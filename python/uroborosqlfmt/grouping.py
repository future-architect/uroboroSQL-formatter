# coding:utf-8
'''
@author: ota
'''
import collections
from sqlparse import sql, tokens as T
from uroborosqlfmt import tokenutils as tu
from uroborosqlfmt.sql import WithinGroupFunctions, Phrase, AscDesc, OffsetFetch, Having, _BaseWords, OverFunctions, \
    When, KeepFunctions, ForUpdate, WaitOrNowait, Union, Join, On, MergeWhen, MergeUpdateInsertClause, ConnectBy, \
    StartWith, With, LimitOffset, SpecialFunctionParameter, Calculation
from uroborosqlfmt.exceptions import SqlFormatterException

def _remove_split_token(token, new_parent):
    parent = token.parent
    tokens = []
    for tkn in token.tokens[:]:
        new_parent.insert_before(token, tkn)
        tkn.parent = new_parent
        tokens.append(tkn)
    parent.tokens.remove(token)
    return tokens

def _move_up_token(token):
    parent = token.parent
    end = parent.tokens[-1]

    after_tokens = parent.tokens_between(token, end)[1:]
    if after_tokens:
        for tkn in after_tokens[::-1]:
            parent.parent.insert_after(parent, tkn)
            tkn.parent = parent.parent
            parent.tokens.remove(tkn)

        parent.parent.group_tokens(parent.__class__, after_tokens)

    parent.parent.insert_after(parent, token)
    token.parent = parent.parent
    parent.tokens.remove(token)

def _move_append_token(new_parent, token):
    parent = token.parent
    parent.tokens.remove(token)
    __remove_empty(parent)
    new_parent.tokens.append(token)
    token.parent = new_parent

def __remove_empty(gtoken):
    if not gtoken.tokens:
        parent = gtoken.parent
        parent.tokens.remove(gtoken)
        __remove_empty(parent)



def re_group_comment(tlist):
    """
        行コメントとブロックコメントが混ざることがあるので分割する処理（バグ？）
        コメントがSQLの最後にあるとコメントとして扱われないのを解消する（バグ？）
    """

    def process_comment(tlist, parent):
        [process_comment(sgroup, tlist) for sgroup in tlist.get_sublists()]

        if tu.is_comment(tlist):

            first = tlist.token_next_by_type(0, T.Comment)
            if not first:
                return


            end_token = get_comment_end(tlist, first)
            if not end_token:
                return

            fst_end_token = end_token

            last = tlist

            idx = tlist.token_index(fst_end_token)
            token = tlist.token_next_by_type(idx + 1, T.Comment)
            while token:
                ws_tokens = tlist.tokens_between(fst_end_token, token, exclude_end=True)[1:]
                for tkn in ws_tokens:
                    tlist.tokens.remove(tkn)
                    parent.insert_after(last, tkn, skip_ws=False)
                    tkn.parent = parent
                    last = tkn

                end_token = get_comment_end(tlist, token)
                tokens = tlist.tokens_between(token, end_token)
                tgroup = tlist.group_tokens(sql.Comment, tokens)
                parent.insert_after(last, tgroup)
                tgroup.parent = parent
                last = tgroup
                tlist.tokens.remove(tgroup)

                idx = tlist.token_index(fst_end_token)
                token = tlist.token_next_by_type(idx + 1, T.Comment)

            ws_tokens = tlist.tokens_between(fst_end_token, tlist.tokens[-1])[1:]
            for tkn in ws_tokens:
                tlist.tokens.remove(tkn)
                parent.insert_after(last, tkn, skip_ws=False)
                tkn.parent = parent
                last = tkn

    def process_not_comment(tlist):
        [process_not_comment(sgroup) for sgroup in tlist.get_sublists()]

        if not tu.is_comment(tlist):
            while True:
                start_token = tlist.token_next_by_type(0, T.Comment)
                if not start_token:
                    return

                end_token = get_comment_end(tlist, start_token)
                if not end_token:
                    return

                tokens = tlist.tokens_between(start_token, end_token)
                tlist.group_tokens(sql.Comment, tokens)

    def get_comment_end(tlist, start):
        if start.value.startswith("--"):
            return start
        elif start.value == "/*":
            tidx = tlist.token_index(start)
            return tlist.token_matching(tidx + 1, [lambda t: t.ttype in T.Comment and t.value == "*/"])

    process_comment = SqlFormatterException.to_wrap_try_except(process_comment, 0)
    process_not_comment = SqlFormatterException.to_wrap_try_except(process_not_comment, 0)

    process_comment(tlist, None)

    process_not_comment(tlist)

def re_group_parenthesis(tlist):
    """
        括弧のグルーピングが外のコメントを巻き込むので外す。（バグ？）
    """

    def _process(tlist, parent):
        [_process(sgroup, tlist) for sgroup in tlist.get_sublists()]

        if tu.is_parenthesis(tlist):
            for token in tlist.tokens[:]:
                if token and tu.is_comment(token) or token.is_whitespace():
                    parent.insert_before(tlist, token, skip_ws=False)
                    tlist.tokens.remove(token)
                else:
                    break
            for token in tlist.tokens[::-1]:
                if token and tu.is_comment(token) or token.is_whitespace():
                    parent.insert_after(tlist, token, skip_ws=False)
                    tlist.tokens.remove(token)
                else:
                    break

    _process = SqlFormatterException.to_wrap_try_except(_process, 0)

    _process(tlist, None)


def re_group_function(stmt):
    """
        Functionのグルーピングで
        FROM(SELECT * FROM ・・・)
        と記述するとFROM句がFunction扱いになるのを修正する（バグ）

        UNION(SELECT * FROM ・・・)
        と記述するとUNION句がFunction扱いになるのを修正する（バグ）

        ON(A = B ・・・)
        と記述するとON句がFunction扱いになるのを修正する（バグ）

        USING(A,B,・・・)
        と記述するとON句がFunction扱いになるのを修正する（バグ）

        SET(A,B,・・・)
        と記述するとSET句がFunction扱いになるのを修正する（バグ）

        INSERT INTO TABLE1(COL1,COL2,COL3)
        及び
        INSERT INTO SC.TABLE1(COL1,COL2,COL3)
        と記述するとTABLE1がFunction扱いになるのを修正する（バグ）

        ROW_NUMBER系のfunctionが何かおかしいことになるので調整
    """

    def _adjust_from_function(tlist, parent):
        """
            FROMの調整
        """
        func_name_token = tu.token_next_enable(tlist)

        _remove_split_token(tlist, parent)

        if tu.is_identifier(func_name_token):
            func_name_tokens = _remove_split_token(func_name_token, parent)
            parent_token = func_name_tokens[0].parent
            while tu.is_identifier_list(parent_token) or tu.is_identifier(parent_token):
                new_parent_token = parent_token.parent
                tokens = parent_token.tokens_between(parent_token.tokens[0], func_name_tokens[-1])
                for tkn in tokens:
                    new_parent_token.insert_before(parent_token, tkn)
                    parent_token.tokens.remove(tkn)
                    tkn.parent = new_parent_token

                parent_token = func_name_tokens[0].parent
        else:
            func_name_tokens = [func_name_token]

        for tkn in func_name_tokens:
            if tu.equals_ignore_case(tkn.value, "FROM") and not tkn.ttype in T.Keyword:
                tkn.ttype = T.Keyword

        parent_token = func_name_tokens[0].parent
        parent_token.insert_after(func_name_tokens[-1], sql.Token(T.Whitespace, " "))

    def _is_illegal_function(tlist):
        func_name_token = tu.token_next_enable(tlist)

        parenthesis = tu.token_next_enable(tlist, func_name_token)
        if not tu.is_parenthesis(parenthesis):
            return True

        other = tu.token_next_enable(tlist, parenthesis)
        if other:
            return True

        return False


    def _adj_illegal_function(tlist, parent):
        func_name_token = tu.token_next_enable(tlist)

        parenthesis = tu.token_next_enable(tlist, func_name_token)
        if not tu.is_parenthesis(parenthesis):
            _remove_split_token(tlist, parent)
            return

        other = tu.token_next_enable(tlist, parenthesis)
        if other:
            _remove_split_token(tlist, parent)
            tokens = parent.tokens_between(func_name_token, parenthesis)
            parent.group_tokens(sql.Function, tokens)
            return

    def _is_insert_into_table_function(tlist, parent):
        if not tu.within_insert_statement(stmt, tlist):
            return False

        prev = tu.token_prev_enable(parent, tlist)
        if not prev:
            return False
        # INSERT INTO TABLE1(COL1,COL2,COL3)を検証
        if tu.is_into_keyword(prev):
            return True

        return False

    def _is_insert_into_table_function2(tlist, parent):
        if not tu.within_insert_statement(stmt, tlist):
            return False

        prev = tu.token_prev_enable(parent, tlist)
        if not prev:
            return False
        # INSERT INTO SC.TABLE1(COL1,COL2,COL3)を検証
        if tu.is_dot(prev):
            prev2 = tu.token_prev_enable(parent, prev)
            if prev2 and tu.is_name_or_keyword(prev2):
                parentparent = parent.parent
                if parentparent:
                    prev = tu.token_prev_enable(parentparent, parent)
                    if prev and tu.is_into_keyword(prev):
                        return True

        return False

    def _split_function(tlist, parent):
        """
            functionを分解
        """
        _remove_split_token(tlist, parent)

    def proc(tlist, parent):
        [proc(sgroup, tlist) for sgroup in tlist.get_sublists()]

        if tu.is_function(tlist):
            if tu.equals_ignore_case(tu.token_next_enable(tlist).value, "FROM"): # FROM句がfunction扱いされている
                _adjust_from_function(tlist, parent)
            elif _is_illegal_function(tlist): # function構成がおかしい。
                _adj_illegal_function(tlist, parent)
            elif _is_insert_into_table_function(tlist, parent):
                _split_function(tlist, parent)
            elif _is_insert_into_table_function2(tlist, parent):
                ftoken = tu.token_next_enable(tlist)
                dot = tu.token_prev_enable(parent, tlist)
                schema_name = tu.token_prev_enable(parent, dot)
                parentparent = parent.parent
                _split_function(tlist, parent)
                parent.group_tokens(sql.Identifier, parent.tokens_between(schema_name, ftoken))

                if tu.is_identifier(parent):
                    _remove_split_token(parent, parentparent)
            elif tu.equals_ignore_case(tu.token_next_enable(tlist).value, "UNION"): # UNIONがfunction扱いされている
                _split_function(tlist, parent)
            elif tu.equals_ignore_case(tu.token_next_enable(tlist).value, "ON"): # ONがfunction扱いされている
                keyword_token = next(tlist.flatten())
                keyword_token.ttype = T.Keyword # なぜかKeywordにならないときがある
                _split_function(tlist, parent)
                # identifier扱いされていることがある
                while keyword_token.parent \
                        and len(keyword_token.parent.tokens) == 1 \
                        and tu.is_identifier(keyword_token.parent):
                    _remove_split_token(keyword_token.parent, keyword_token.parent.parent)
            elif tu.equals_ignore_case(tu.token_next_enable(tlist).value, "USING"): # USINGがfunction扱いされている
                _split_function(tlist, parent)
            elif tu.equals_ignore_case(tu.token_next_enable(tlist).value, "SET"): # SETがfunction扱いされている
                keyword_token = next(tlist.flatten())
                keyword_token.ttype = T.Keyword # なぜかKeywordにならないときがある
                _split_function(tlist, parent)
                # identifier扱いされていることがある
                while keyword_token.parent and \
                        len(keyword_token.parent.tokens) == 1 and \
                        tu.is_identifier(keyword_token.parent):
                    _remove_split_token(keyword_token.parent, keyword_token.parent.parent)

    proc = SqlFormatterException.to_wrap_try_except(proc, 0)
    proc(stmt, None)

def re_group_case(tlist):
    """
        CASEのグルーピングが外のコメントを巻き込むので外す。（バグ？）
    """
    def _process(tlist, parent):
        [_process(sgroup, tlist) for sgroup in tlist.get_sublists()]

        if tu.is_case(tlist):
            for token in tlist.tokens[:]:
                if token and tu.is_comment(token) or token.is_whitespace():
                    parent.insert_before(tlist, token, skip_ws=False)
                    tlist.tokens.remove(token)
                else:
                    break
            for token in tlist.tokens[::-1]:
                if token and tu.is_comment(token) or token.is_whitespace():
                    parent.insert_after(tlist, token, skip_ws=False)
                    tlist.tokens.remove(token)
                else:
                    break

    _process = SqlFormatterException.to_wrap_try_except(_process, 0)
    _process(tlist, None)



def re_group_tree(tlist):
    """
        ツリーを再構築
    """
    [re_group_tree(sgroup) for sgroup in tlist.get_sublists()]

    for tkn in tlist.tokens:
        tkn.parent = tlist

class _WordsTokenHitTests(object):
    # pylint: disable=unused-argument
    """
        _BaseWordsGroupingｂのグルーピング判定の基底クラス
    """
    def first_test(self, token):
        return False

    def get_next_test(self, tokens):
        return lambda t: False

    def is_completed(self, tokens):
        return False

    def get_add_prev_tokens(self, tokens, prevs):
        return []

    def is_completed_group(self, tokens, curr_stmt):
        return self.is_completed(tokens)

    def _test_word(self, word, token):
        return tu.equals_ignore_case(token.value, word) and (token.ttype in T.Name or token.ttype in T.Keyword)

    def adj_tokens(self, tokens, **options):
        return tokens

    def init_group_token(self, token):
        pass
    # pylint: enable=unused-argument

class _SimpleWordsTokenHitTests(_WordsTokenHitTests):
    """
        条件リストからシンプルに判定する_WordsTokenHitTests
    """
    def __init__(self, gjs):
        self.list = []
        for jdg in gjs:
            self.list.append(self.__to_hit_test(jdg))

    def first_test(self, token):
        return self.list[0](token)

    def get_next_test(self, tokens):
        return self.list[len(tokens)]

    def is_completed(self, tokens):
        return len(tokens) >= len(self.list)

    def __to_hit_test(self, jdg):
        if isinstance(jdg, str):
            return lambda t: self._test_word(jdg, t)
        elif isinstance(jdg, type(T.Token)):
            return lambda t: t.ttype in jdg
        elif isinstance(jdg, collections.Iterable):
            def itr_hit_test(tkn):
                for elm in jdg:
                    if self.__to_hit_test(elm)(tkn):
                        return True
                return False
            return itr_hit_test
        else:
            return jdg


class _BaseWordsGrouping(object):
    GROUP_JUDGE_SET = []

    def __init__(self):
        self.__hit_tests = list(self.__to_hit_test_set(self.GROUP_JUDGE_SET))
        self._process = SqlFormatterException.to_wrap_try_except(self._process, 0)
        self.curr_stmt = None

    def process(self, stmt):
        self.curr_stmt = stmt
        self._process(stmt)

    def _process(self, tlist): # pylint: disable=method-hidden
        def token_next(token, func):
            nexts = tu.flatten_tokens_next(self.curr_stmt, token)
            for tkn in nexts:
                return tu.token_top_matching(tkn, token, func)

        def concat_next(tokenset):
            next_token = token_next(tokenset.tokens[-1], tokenset.is_hit_neednext)
            if not next_token:
                return None

            tokenset.append(next_token)

            return next_token

        self0 = self

        class TokenSet(object):
            def __init__(self, tokens, hittests):
                self.tokens = tokens
                self.target_tokens = tokens[:]
                self.hittests = hittests

            def next_judge(self):
                return self.hittests.get_next_test(self.target_tokens)

            def append(self, token):
                self.tokens.append(token)

                if tu.is_enable(token) and self.next_judge()(token):
                    self.target_tokens.append(token)

            def is_completed(self):
                return self.hittests.is_completed(self.target_tokens)

            def add_prev_tokens(self, prevs):
                """
                    前tokenを含める処理
                """
                adds = self.hittests.get_add_prev_tokens(self.target_tokens, prevs)
                self.tokens = adds + self.tokens
                self.target_tokens = adds + self.target_tokens
                return len(adds)

            def is_completed_group(self):
                return self.hittests.is_completed_group(self.target_tokens, self0.curr_stmt)

            def is_hit_neednext(self, token):
                if not tu.is_enable(token):
                    return True

                hittest = self.next_judge()
                return hittest(token)

            def grouping(self):
                tokens = self.hittests.adj_tokens(self.tokens,
                    flatten_tokens_next = lambda tkn: tu.flatten_tokens_next(self0.curr_stmt, tkn),
                )
                tfst = tokens[0]

                cls = self0.get_group_class()
                tgp = tlist.group_tokens(cls, [tfst])
                if isinstance(tgp, _BaseWords):
                    tgp._setupinit(self.target_tokens)

                for tkn in tokens[1:]:
                    _move_append_token(tgp, tkn)

                tgp.value = tgp._to_string()
                self.hittests.init_group_token(tgp)
                return tgp

        if not isinstance(tlist, self.get_group_class()):
            i = 0
            while len(tlist.tokens) > i:
                token = tlist.tokens[i]
                i += 1
                for idx, hittests in enumerate(self.__hit_tests):
                    if hittests.first_test(token):
                        tokenset = TokenSet([token], hittests)
                        while not tokenset.is_completed():
                            if not concat_next(tokenset):
                                break
                        addlen = tokenset.add_prev_tokens(tlist.tokens[0:i - 1])
                        if tokenset.is_completed_group():
                            i -= addlen
                            tgp = tokenset.grouping()
                            self.init_group_token(tgp, idx)
                            self._adjust_identifier(tgp, tlist)
                            break

        [self._process(sgroup) for sgroup in tlist.get_sublists()]


    def get_group_class(self):
        pass

    def init_group_token(self, token, idx):
        pass

    def __to_hit_test_set(self, group_judge_set):
        for gjs in group_judge_set:
            yield self.__to_hit_tests(gjs)

    def __to_hit_tests(self, gjs):
        if isinstance(gjs, _WordsTokenHitTests):
            return gjs
        return _SimpleWordsTokenHitTests(gjs)

    def _adjust_identifier(self, gptoken, tlist):
        if not tu.is_identifier(tlist):
            return

        def token_next_enable(token, func):
            nexts = tu.flatten_tokens_next(self.curr_stmt, token)
            for tkn in nexts:
                if tu.is_enable(tkn):
                    return tu.token_top_matching(tkn, token, func)

        next_comma = token_next_enable(gptoken, tu.is_comma)
        if not next_comma or not tu.is_identifier_list(next_comma.parent):
            return

        if tu.is_identifier_list(tlist.parent):
            if tlist.parent == next_comma.parent:
                return
            identifier_list = tlist.parent
            for tkn in next_comma.parent.tokens[:]:
                _move_append_token(identifier_list, tkn)
        else:
            identifier_list = tlist.parent.group_tokens(sql.IdentifierList, [tlist])
            for tkn in next_comma.parent.tokens[:]:
                _move_append_token(identifier_list, tkn)

        self._process(identifier_list)


class GroupingWithinGroupFunctions(_BaseWordsGrouping):
    """
        LISTAGG等のWITHIN GROUPのつく関数の
        グルーピングを拡張
    """
    GROUP_JUDGE_SET = [
        (tu.is_function,
         "WITHIN",
         lambda t: tu.is_function(t) and (tu.equals_ignore_case(tu.token_next_enable(t).value, "GROUP")),
         ),
        (tu.is_function,
         "WITHIN",
         "GROUP",
         tu.is_parenthesis),
    ]

    def get_group_class(self):
        return WithinGroupFunctions

    def init_group_token(self, token, idx):
        if idx == 0:
            token._main_function = token._token_word(0)
            token._within = token._token_word(1)
            token._group = token._token_word(2)
        elif idx == 1:
            token._main_function = token._token_word(0)
            token._within = token._token_word(1)
            tgrp = token._token_word(2)
            tprn = token._token_word(3)
            token._group = token.group_tokens(sql.Function, token.tokens_between(tgrp, tprn))

class GroupingPhrase(_BaseWordsGrouping):
    """
        Phraseのグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        ("GROUP", "BY"),
        ("ORDER", "BY"),
        ("PARTITION", "BY"),
        ("DENSE_RANK", ("LAST", "FIRST")),
        ("CONNECT", "BY"),
        ("START", "WITH"),
    ]

    def get_group_class(self):
        return Phrase

    def init_group_token(self, token, idx):
        parent = token.parent
        if tu.is_identifier(parent):
            elm = tu.token_next_enable(parent)
            if (elm == token) and (not tu.token_next_enable(parent, elm)):
                _remove_split_token(parent, parent.parent)

class GroupingAscDesc(_BaseWordsGrouping):
    """
        ASC DESCのグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        (("ASC", "DESC"), "NULLS", ("FIRST", "LAST")),
        ("NULLS", ("FIRST", "LAST")),
        ("ASC",),
        ("DESC",),
    ]

    def get_group_class(self):
        return AscDesc




class GroupingOffsetFetch(_BaseWordsGrouping):
    """
        OFFSET句、FETCH句のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        ("OFFSET", tu.is_number_candidate, "ROWS"),
        ("FETCH", ("FIRST", "NEXT"), tu.is_number_candidate, "ROWS", "ONLY"),
        ("FETCH", ("FIRST", "NEXT"), tu.is_number_candidate, "ROWS", "WITH", "TIES"),
        ("FETCH", ("FIRST", "NEXT"), tu.is_number_candidate, "PERCENT", "ROWS", "ONLY"),
        ("FETCH", ("FIRST", "NEXT"), tu.is_number_candidate, "PERCENT", "ROWS", "WITH", "TIES"),
    ]

#     [OFFSET <行数> ROWS] FETCH {FIRST|NEXT} [<行数>|<パーセント> PERCENT] ROWS {ONLY|WITH TIES} ;

    def get_group_class(self):
        return OffsetFetch

class GroupingLimitOffset(_BaseWordsGrouping):
    """
        LIMIT・OFFSET句のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        ("LIMIT", tu.is_number_candidate, tu.is_comma, tu.is_number_candidate),
        ("LIMIT", lambda t: tu.is_identifier_list(t) and (len(t.get_identifiers()) == 2)),
        ("LIMIT", tu.is_number_candidate, "OFFSET", tu.is_number_candidate),
        ("LIMIT", tu.is_number_candidate),
    ]

    def get_group_class(self):
        return LimitOffset

class GroupingOverFunctions(_BaseWordsGrouping):
    """
        ROW_NUMBER句などのグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        (
            tu.is_function,
            lambda t: tu.is_function(t) and (tu.equals_ignore_case(tu.token_next_enable(t).value, "OVER")),
        ),
    ]

    def get_group_class(self):
        return OverFunctions

class GroupingKeepFunctions(_BaseWordsGrouping):
    """
        ROW_NUMBER句などのグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        (
            tu.is_function,
            lambda t: tu.is_function(t) and (tu.equals_ignore_case(tu.token_next_enable(t).value, "KEEP")),
        ),
    ]

    def get_group_class(self):
        return KeepFunctions

class GroupingWaitOrNowait(_BaseWordsGrouping):
    """
        WAIT / NOWAITのグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        ("WAIT", tu.is_literal),
        (("WAIT", "NOWAIT"), ),
    ]

    def get_group_class(self):
        return WaitOrNowait

    def init_group_token(self, token, idx):
        while tu.is_identifier(token.parent) or tu.is_identifier_list(token.parent):
            _move_up_token(token)

class _ForUpdateWordsTokenHitTests(_WordsTokenHitTests):

    def __init__(self, wait_or_nowait):
        self.wait_or_nowait = wait_or_nowait

    def first_test(self, token):
        return self._test_word("FOR", token)

    def second_test(self, token):
        return self._test_word("UPDATE", token)

    def third_test(self, token):
        return self._test_word("OF", token)

    def get_next_test(self, tokens):
        length = len(tokens)
        if length == 1:
            return self.second_test
        elif length == 2:
            return self.third_test

        return lambda t: self.test_others(tokens[-1], t)

    def test_others(self, prev, token):
        if self.wait_or_nowait:
            if tu.is_waitornowait(token):
                return True

        if self._test_word("OF", prev) or tu.is_comma(prev):
            return tu.is_identifier(token) or tu.is_identifier_list(token)

        return tu.is_comma(token)

    def is_completed(self, tokens):
        length = len(tokens)

        if length < 4:
            return False

        if tu.is_comma(tokens[-1]):
            return False

        if self._test_word("OF", tokens[-1]):
            return False

        if self.wait_or_nowait:
            if length >= 4 and tu.is_waitornowait(tokens[-1]):
                return True

        return False


    def is_completed_group(self, tokens, curr_stmt):
        length = len(tokens)

        if length < 4:
            return False

        if tu.is_comma(tokens[-1]):
            return False

        if self._test_word("OF", tokens[-1]):
            return False

        if self.wait_or_nowait:
            if length >= 4 and tu.is_waitornowait(tokens[-1]):
                return True

        return True

class GroupingForUpdate(_BaseWordsGrouping):
    """
        FOR UPDATE句のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        _ForUpdateWordsTokenHitTests(True),
        _ForUpdateWordsTokenHitTests(False),
        ("FOR", "UPDATE", tu.is_waitornowait),
        ("FOR", "UPDATE"),
    ]

    def get_group_class(self):
        return ForUpdate

    def init_group_token(self, token, idx):
        token.get_update().ttype = T.Keyword

class GroupingUnion(_BaseWordsGrouping):
    """
        UNION系のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        ("UNION", "ALL"),
        ("UNION",),
        ("MINUS",),
        ("EXCEPT", "ALL"),
        ("EXCEPT",),
        ("INTERSECT",),
    ]

    def get_group_class(self):
        return Union


class _JoinNonUsingWordsTokenHitTests(_WordsTokenHitTests):
    def __init__(self, using_target):
        self.using_target = using_target

    def _is_join_keyword(self, token):
        """
            JOIN判定
        """
        return tu.endswith_ignore_case(token.value, "JOIN") \
                    and (token.ttype in T.Name or token.ttype in T.Keyword)

    def __get_joins(self, tokens):
        """
            JOIN句
        """

        joins = []
        completed = False

        first_token = tokens[0]
        if self._is_join_keyword(first_token):
            joins.append(first_token)
            completed = True
        elif self._test_word("NATURAL", first_token):
            joins.append(first_token)
            if len(tokens) > 1:
                second_token = tokens[1]
                if self._is_join_keyword(second_token):
                    completed = True
                    joins.append(second_token)
        else:
            return [], tokens[:], False # JOINではない


        return joins, tokens[len(joins):], completed

    def __get_identifier(self, tokens):
        """
            identifier
        """
        def get(index):
            if len(tokens) > index:
                return tokens[index]
            return None

        index = 0


        identifier = []

        tkn = get(index)
        if not tkn:
            return [], tokens[:], False # JOINではない

        # table name or query
        if tkn.ttype in T.Name:
            identifier.append(tkn)
            nexttkn = get(index + 1)
            if nexttkn and tu.is_dot(nexttkn): # SCHEMA.TABLE ?
                index += 1
                identifier.append(nexttkn)
                nexttkn = get(index + 1)
                if not nexttkn:
                    return identifier, tokens[len(identifier):], False # 未完成
                if nexttkn.ttype in T.Name:
                    index += 1
                    identifier.append(nexttkn)
                else:
                    return [], tokens[:], False # JOINではない
        elif tu.is_parenthesis(tkn):
            identifier.append(tkn)
        else:
            return [], tokens[:], False # JOINではない

        index += 1

        tkn = get(index)
        if not tkn:
            return identifier, tokens[len(identifier):], True # 終了

        # AS
        if tu.is_as_keyword(tkn):
            identifier.append(tkn)
            index += 1
            tkn = get(index)

        if not tkn:
            return identifier, tokens[len(identifier):], False # AS の次が無い

        # ALIAS
        if not tkn.ttype in T.Name:
            return [], tokens[:], False # JOINではない

        if self._test_word("USING", tkn):
            return identifier, tokens[len(identifier):], True # 終了


        identifier.append(tkn)
        return identifier, tokens[len(identifier):], True # 終了


    def __get_using(self, tokens):

        if tokens:
            token = tokens[0]
            if self._test_word("USING", token):
                return [token], tokens[1:], True
        return [], tokens[:], False # USINGは存在しない

    def __get_using_parenthesis(self, tokens):

        if tokens:
            token = tokens[0]
            if tu.is_parenthesis(token):
                return [token], tokens[1:], True
        return [], tokens[:], False # USINGの次の括弧は存在しない

    def __test(self, tokens):

        joins, tokens, _ = self.__get_joins(tokens)
        if not joins:
            return False
        if not tokens:
            return True

        identifier, tokens, _ = self.__get_identifier(tokens)

        if not identifier:
            return False
        if not tokens:
            # すべて消化されたいる場合OK
            return True

        if not self.using_target:
            return False

        using, tokens, _ = self.__get_using(tokens)

        if not using:
            return False
        if not tokens:
            return True

        using_parenthesis, tokens, _ = self.__get_using_parenthesis(tokens)

        if not using_parenthesis:
            return False
        if not tokens:
            # すべて消化されたいる場合OK
            return True

        return False

    def first_test(self, token):
        joins, _, _ = self.__get_joins([token])
        return joins

    def get_next_test(self, tokens):
        return lambda t: self.__test(tokens + [t])

    def is_completed(self, tokens):
        return False

    def get_add_prev_tokens(self, tokens, prevs):
        return []

    def is_completed_group(self, tokens, curr_stmt):
        joins, tokens, completed = self.__get_joins(tokens)
        if (not joins) or (not completed):
            return False

        identifier, tokens, completed = self.__get_identifier(tokens)

        if (not identifier) or (not completed):
            return False

        if not self.using_target:
            if not tokens:
                # すべて消化されている場合OK
                return True

        using, tokens, completed = self.__get_using(tokens)

        if (not using) or (not completed):
            return False

        using_parenthesis, tokens, completed = self.__get_using_parenthesis(tokens)

        if (not using_parenthesis) or (not completed):
            return False
        if not tokens:
            # すべて消化されている場合OK
            return True

        return False



    def __get_next_disable(self, flatten_tokens_next, tgt):
        for tkn in flatten_tokens_next(tgt):
            if tu.is_enable(tkn):
                return None
            if tkn.parent and tu.is_comment(tkn.parent):
                return tkn.parent
            else:
                return tkn


    def adj_tokens(self, tokens, flatten_tokens_next, **_):
        """
            後ろのコメント・空白を含めてgroupingする
        """
        org_tokens = tokens
        _, tokens, _ = self.__get_joins(tokens)
        identifier, tokens, _ = self.__get_identifier(tokens)
        if tokens:
            return org_tokens

        # identifierで終了している場合のみ実行

        need_adj = False
        adj_tokens = []
        tkn = self.__get_next_disable(flatten_tokens_next, identifier[-1])
        while tkn:
            if tu.is_comment(tkn):
                need_adj = True
            adj_tokens.append(tkn)
            tkn = self.__get_next_disable(flatten_tokens_next, adj_tokens[-1])

        if need_adj:
            return org_tokens + adj_tokens
        else:
            return org_tokens

    def __build_useingjoin_value(self, token, tokens):
        text = tokens[0].value
        for tkn in tokens[1:]:
            text += tkn.value
            token.tokens.remove(tkn)
        return text

    def __bind_tokens(self, token, tokens):
        token.usingtoken = None
        token.usingparenthesistoken = None
        joins, tokens, _ = self.__get_joins(tokens)
        identifier, tokens, _ = self.__get_identifier(tokens)

        token.jointoken = joins[0]
        token.jointoken.value = self.__build_useingjoin_value(token, token.tokens_between(joins[0], joins[-1]))

        if not self.using_target:
            token.identifiertoken = token.group_tokens(
                    sql.Identifier,
                    token.tokens_between(identifier[0], token.tokens[-1])

                )
            return
        else:
            using, tokens, _ = self.__get_using(tokens)
            using_parenthesis, tokens, _ = self.__get_using_parenthesis(tokens)
            token.identifiertoken = token.group_tokens(
                    sql.Identifier,
                    token.tokens_between(identifier[0], using[0], exclude_end=True)

                )

            token.usingtoken = using[0]
            token.usingparenthesistoken = using_parenthesis[0]

    def init_group_token(self, token):
        token.usingtoken = None
        token.usingparenthesistoken = None

        self.__bind_tokens(token, token.get_target_tokens())





class GroupingJoin(_BaseWordsGrouping):
    """
        JOIN系のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        _JoinNonUsingWordsTokenHitTests(using_target=True),
        _JoinNonUsingWordsTokenHitTests(using_target=False)
    ]


    def get_group_class(self):
        return Join



class GroupingMergeWhen(_BaseWordsGrouping):
    """
        MERGEのWHEN句のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        ("WHEN", "NOT", "MATCHED", "THEN"),
        ("WHEN", "MATCHED", "THEN"),
    ]

    def get_group_class(self):
        return MergeWhen

class _WithSelectionTokenHitTests(_WordsTokenHitTests):

    def __init__(self):
        pass

    def first_test(self, token):
        return self._test_word("WITH", token)

    def single_identifier_test(self, token):
        if not tu.is_identifier(token):
            return (not token.is_group()) and token.ttype in T.Name

        if len(token.tokens) != 1:
            return False

        return not token.tokens[0].is_group()

    def identifier_next_test(self, token):
        return tu.is_as_keyword(token) or tu.is_parenthesis(token)

    def query_parenthesis_test(self, token):
        return tu.is_dmlddl_parenthesis(token)

    def get_next_test(self, tokens):
        lasttoken = tokens[-1]
        if self.first_test(lasttoken):
            return self.single_identifier_test

        if self.single_identifier_test(lasttoken):
            return self.identifier_next_test

        if tu.is_as_keyword(lasttoken):
            return self.query_parenthesis_test

        if tu.is_parenthesis(lasttoken):
            if self.single_identifier_test(tokens[-2]):
                return tu.is_as_keyword
            elif self.query_parenthesis_test(lasttoken):
                return tu.is_comma

        if tu.is_comma(lasttoken):
            return self.single_identifier_test

        return lambda x: False


    def is_completed(self, tokens):
        return False


    def is_completed_group(self, tokens, curr_stmt):
        lasttoken = tokens[-1]
        return self.query_parenthesis_test(lasttoken)


    def init_group_token(self, token):
        tokens = token.get_target_tokens()
        with_token = tokens[0]
        start_prev = with_token
        end = None
        for tkn in tokens[1:]:
            if tu.is_comma(tkn):
                start = tu.token_next_enable(token, start_prev)
                token.group_tokens(sql.Identifier, token.tokens_between(start, end))
                start_prev = tkn
                continue
            end = tkn

        start = tu.token_next_enable(token, with_token)
        end = tu.token_prev_enable(token)
        token.group_tokens(sql.IdentifierList, token.tokens_between(start, end))


class GroupingWith(_BaseWordsGrouping):
    """
        WITH句のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        _WithSelectionTokenHitTests(),
    ]

    def get_group_class(self):
        return With



class _SpecialFunctionParameterTokenHitTests(_SimpleWordsTokenHitTests):

    def __init__(self, func_name, gjs):
        self.func_name = func_name
        super(_SpecialFunctionParameterTokenHitTests, self).__init__(gjs)

    def __within_target_function(self, token):
        if token.parent and tu.is_parenthesis(token.parent):
            tgtfunc = token.parent.parent
            if tgtfunc and tu.is_function(tgtfunc):
                fst = tu.token_next_enable(tgtfunc)
                return tu.equals_ignore_case(fst.value, self.func_name)

        return False

    def first_test(self, token):
        return super(_SpecialFunctionParameterTokenHitTests, self).first_test(token) \
                and self.__within_target_function(token)

    def get_next_test(self, tokens):
        fnc = super(_SpecialFunctionParameterTokenHitTests, self).get_next_test(tokens)
        return lambda t: fnc(t) and self.__within_target_function(t)


    def is_completed(self, tokens):
        return super(_SpecialFunctionParameterTokenHitTests, self).is_completed(tokens)


    def is_completed_group(self, tokens, curr_stmt):
        if not super(_SpecialFunctionParameterTokenHitTests, self).is_completed_group(tokens, curr_stmt):
            return False
        last = tokens[-1]
        for tkn in tu.flatten_tokens_next(curr_stmt, last):
            if tu.is_enable(tkn):
                return tu.is_close_punctuation(tkn)
        return False


class GroupingSpecialFunctionParameter(_BaseWordsGrouping):
    """
        特殊な関数のグルーピングを拡張
        ANSIのTRIM
        ORACLEのTRIM・EXTRACT
        PostgreSQLのSUBSTRING
        など
    """

    GROUP_JUDGE_SET = [
        # TRIM ( [ LEADING | TRAILING | BOTH ] trim_char FROM string ) 標準SQL
        _SpecialFunctionParameterTokenHitTests("TRIM", (
            ("LEADING", "TRAILING", "BOTH"),
            tu.is_string_candidate,
            "FROM",
            tu.is_string_candidate,
        )),
        # TRIM ( trim_char FROM string )
        _SpecialFunctionParameterTokenHitTests("TRIM", (
            tu.is_string_candidate,
            "FROM",
            tu.is_string_candidate,
        )),
        # EXTRACT ( element FROM datetime )
        _SpecialFunctionParameterTokenHitTests("EXTRACT", (
            tu.is_value_candidate,
            "FROM",
            tu.is_identifier,
        )),
        # overlay(string placing string from int [for int])
        _SpecialFunctionParameterTokenHitTests("overlay", (
            tu.is_string_candidate,
            "placing",
            tu.is_string_candidate,
            "from",
            tu.is_number_candidate,
            "for",
            tu.is_number_candidate,
        )),
        _SpecialFunctionParameterTokenHitTests("overlay", (
            tu.is_string_candidate,
            "placing",
            tu.is_string_candidate,
            "from",
            tu.is_number_candidate,
        )),
        # position(substring in string)
        _SpecialFunctionParameterTokenHitTests("position", (
            tu.is_string_candidate,
            "in",
            tu.is_string_candidate,
        )),
        # substring(string [from int] [for int])
        _SpecialFunctionParameterTokenHitTests("substring", (
            tu.is_string_candidate,
            "from",
            tu.is_number_candidate,
            "for",
            tu.is_number_candidate,
        )),
        _SpecialFunctionParameterTokenHitTests("substring", (
            tu.is_string_candidate,
            "from",
            tu.is_number_candidate,
        )),
        # substring(string from pattern)
        _SpecialFunctionParameterTokenHitTests("substring", (
            tu.is_string_candidate,
            "from",
            tu.is_string_candidate,
        )),
        # substring(string from pattern for escape)
        _SpecialFunctionParameterTokenHitTests("substring", (
            tu.is_string_candidate,
            "from",
            tu.is_string_candidate,
            "for",
            tu.is_string_candidate,
        )),
    ]


    def get_group_class(self):
        return SpecialFunctionParameter


    def init_group_token(self, token, idx):
        pass

class _GroupingCalculationTokenHitTests(_WordsTokenHitTests):

    def first_test(self, token):
        return tu.is_calc_operator(token)

    def get_next_test(self, tokens):
        last = tokens[-1]
        if tu.is_value_candidate(last):
            return tu.is_calc_operator
        if tu.is_calc_operator(last):
            return tu.is_value_candidate

        return lambda t:False


    def is_completed(self, tokens):
        return False

    # is_value_candidateから演算を始めると処理が遅いのであとで頭に追加する
    def get_add_prev_tokens(self, tokens, prevs):
        for i, tkn in list(enumerate(prevs))[::-1]:
            if tu.is_enable(tkn):
                if tu.is_value_candidate(tkn):
                    return prevs[i:]
                break
        return []

    def is_completed_group(self, tokens, curr_stmt):
        first = tokens[0]
        if not tu.is_value_candidate(first):
            return False
        last = tokens[-1]
        if not tu.is_value_candidate(last):
            return False
        tokens = [t for t in tokens if tu.is_enable]
        return len(tokens) > 2

    def adj_tokens(self, tokens, **_):
        for i, tkn in list(enumerate(tokens))[::-1]:
            if tu.is_enable(tkn):
                return tokens[:i + 1]
        return tokens


class GroupingCalculation(_BaseWordsGrouping):
    """
        計算値のグルーピングを拡張
    """

    GROUP_JUDGE_SET = [
        _GroupingCalculationTokenHitTests(),
    ]


    def get_group_class(self):
        return Calculation

    def init_group_token(self, token, idx):
        pass

class AdjustGroupingFunction(_BaseWordsGrouping):
    """
        スペースが入ったとき、Function判定されないので、Functionのグルーピングを調整
        現状は下記の関数のみ対応。（T.Nameなどで当ててしまうとINSERT句で間違った判定がされる）
        ・COUNT
        ・EXISTS
        ・SUM
        ・MAX
        ・MIN
    """

    GROUP_JUDGE_SET = [
        (lambda t: tu.equals_ignore_case(t.value, "COUNT") \
                and (t.ttype in T.Name or t.ttype in T.Keyword) \
                and (not tu.is_identifier(t.parent)) ,
            tu.is_parenthesis),
        (lambda t: tu.equals_ignore_case(t.value, "EXISTS") \
                and (t.ttype in T.Name or t.ttype in T.Keyword) \
                and (not tu.is_identifier(t.parent)),
            tu.is_parenthesis),
        (lambda t: tu.equals_ignore_case(t.value, "SUM") \
                and (t.ttype in T.Name or t.ttype in T.Keyword) \
                and (not tu.is_identifier(t.parent)),
            tu.is_parenthesis),
        (lambda t: tu.equals_ignore_case(t.value, "MAX") \
                and (t.ttype in T.Name or t.ttype in T.Keyword) \
                and (not tu.is_identifier(t.parent)),
            tu.is_parenthesis),
        (lambda t: tu.equals_ignore_case(t.value, "MIN") \
                and (t.ttype in T.Name or t.ttype in T.Keyword) \
                and (not tu.is_identifier(t.parent)),
            tu.is_parenthesis),
    ]

    def get_group_class(self):
        return sql.Function



def group_having(tlist):
    def end_match(token):
        stopwords = ('ORDER', 'GROUP', 'LIMIT', 'UNION', 'EXCEPT', 'HAVING',
                     'WHEN', # for Oracle10g merge
                     'CONNECT', # for Oracle connect by
                     )
        if token.match(T.Keyword, stopwords):
            return True
        if token.match(T.DML, ('DELETE')): # for Oracle10g merge
            return True
        if token.match(T.DML, ('START')): # for Oracle connect by
            return True

        return False

    def proc(tlist):
        [proc(sgroup) for sgroup in tlist.get_sublists()
         if not isinstance(sgroup, Having)]
        idx = 0
        token = tlist.token_next_match(idx, T.Keyword, 'HAVING')
        while token:
            tidx = tlist.token_index(token)
            end = tlist.token_matching(tidx + 1, (end_match, ))
            if end is None:
                end = tlist._groupable_tokens[-1]
            else:
                end = tlist.tokens[tlist.token_index(end) - 1]
            tgroup = tlist.group_tokens(Having,
                                       tlist.tokens_between(token, end),
                                       ignore_ws=True)
            idx = tlist.token_index(tgroup)
            token = tlist.token_next_match(idx, T.Keyword, 'HAVING')

    proc = SqlFormatterException.to_wrap_try_except(proc, 0)
    proc(tlist)

def group_when(tlist):
    def proc(tlist):
        [proc(sgroup) for sgroup in tlist.get_sublists()
         if not isinstance(sgroup, When)]

        if not tu.is_case(tlist):
            return
        idx = 0
        token = tlist.token_next_match(idx, T.Keyword, 'WHEN')
        stopwords = ('THEN', 'END')
        while token:
            tidx = tlist.token_index(token)
            end = tlist.token_next_match(tidx + 1, T.Keyword, stopwords)
            if end is None:
                end = tlist._groupable_tokens[-1]
            else:
                end = tlist.tokens[tlist.token_index(end) - 1]
            tgroup = tlist.group_tokens(When,
                                       tlist.tokens_between(token, end),
                                       ignore_ws=True)
            idx = tlist.token_index(tgroup)
            token = tlist.token_next_match(idx, T.Keyword, 'WHEN')

    proc = SqlFormatterException.to_wrap_try_except(proc, 0)
    proc(tlist)

def group_on(tlist):

    def end_match(token):
        stopwords = ('WHERE', 'ORDER', 'GROUP', 'LIMIT', 'UNION', 'EXCEPT', 'HAVING',
                     'WHEN', # for Oracle10g merge
                     'CONNECT', # for Oracle connect by
                     )
        if token.match(T.Keyword, stopwords):
            return True

        if tu.is_phrase(token):
            if token.match_phrase(('ORDER', 'BY')) or token.match_phrase(('GROUP', 'BY')):
                return True


        return tu.is_join(token) or tu.is_mergewhen(token)

    def proc(tlist):
        [proc(sgroup) for sgroup in tlist.get_sublists()
         if not isinstance(sgroup, On)]
        idx = 0
        token = tlist.token_next_match(idx, T.Keyword, 'ON')

        while token:
            tidx = tlist.token_index(token)
            end = tlist.token_matching(tidx + 1, (end_match,))
            if end is None:
                end = tlist._groupable_tokens[-1]
            else:
                end = tlist.tokens[tlist.token_index(end) - 1]
            tgroup = tlist.group_tokens(On,
                                       tlist.tokens_between(token, end),
                                       ignore_ws=True)
            idx = tlist.token_index(tgroup)
            token = tlist.token_next_match(idx, T.Keyword, 'ON')

    proc = SqlFormatterException.to_wrap_try_except(proc, 0)
    proc(tlist)

def group_connectby_startwith(tlist):
    def start_match(token):
        if tu.is_phrase(token):
            return token.match_phrase(("CONNECT", "BY")) or token.match_phrase(("START", "WITH"))


    def end_match(token):
        stopwords = ('ORDER', 'GROUP', 'LIMIT', 'UNION', 'EXCEPT', 'HAVING',
                     'WHEN', # for Oracle10g merge
                     'CONNECT', # for Oracle connect by
                     )
        if token.match(T.Keyword, stopwords):
            return True
        if token.match(T.DML, ('DELETE')): # for Oracle10g merge
            return True
        if token.match(T.DML, ('START')): # for Oracle connect by
            return True

        if tu.is_phrase(token):
            if token.match_phrase(("CONNECT", "BY")) or token.match_phrase(("START", "WITH")):
                return True

        return False

    def proc(tlist):
        [proc(sgroup) for sgroup in tlist.get_sublists()
         if (not isinstance(sgroup, ConnectBy)) and (not isinstance(sgroup, StartWith))]
        idx = 0
        token = tlist.token_matching(idx, (start_match, ))
        while token:
            tidx = tlist.token_index(token)
            end = tlist.token_matching(tidx + 1, (end_match, ))
            if end is None:
                end = tlist._groupable_tokens[-1]
            else:
                end = tlist.tokens[tlist.token_index(end) - 1]

            group_class = None
            if token.match_phrase(("CONNECT", "BY")):
                group_class = ConnectBy
            elif token.match_phrase(("START", "WITH")):
                group_class = StartWith
            tgroup = tlist.group_tokens(group_class,
                                       tlist.tokens_between(token, end),
                                       ignore_ws=True)

            idx = tlist.token_index(tgroup)
            token = tlist.token_matching(idx, (start_match, ))

    proc = SqlFormatterException.to_wrap_try_except(proc, 0)
    proc(tlist)

def group_mergeupdateinsertclause(tlist):

    def get_start_match(tlist):
        token = tlist.token_matching(0, (tu.is_mergewhen,))
        if token:
            return tu.token_next_enable(tlist, token)
        return None

    def get_start_match2(tlist, idx):
        token = tlist.token_matching(idx, (tu.is_mergewhen, tu.is_delete_dml))
        if token:
            if tu.is_delete_dml(token):
                return token
            return tu.token_next_enable(tlist, token)
        return None

    def end_match(token):
        return tu.is_mergewhen(token) or tu.is_delete_dml(token)

    def proc(tlist):
        [proc(sgroup) for sgroup in tlist.get_sublists()
         if not isinstance(sgroup, MergeUpdateInsertClause)]
        token = get_start_match(tlist)

        while token:
            tidx = tlist.token_index(token)
            end = tlist.token_matching(tidx + 1, (end_match,))
            if end is None:
                end = tlist._groupable_tokens[-1]
            else:
                end = tlist.tokens[tlist.token_index(end) - 1]
            tgroup = tlist.group_tokens(MergeUpdateInsertClause,
                                       tlist.tokens_between(token, end),
                                       ignore_ws=True)
            idx = tlist.token_index(tgroup)
            token = get_start_match2(tlist, idx)

    proc = SqlFormatterException.to_wrap_try_except(proc, 0)
    proc(tlist)



def adj_group_comparison(tlist):
    """
        Comparisonのグルーピングでコメントがあると綺麗に整わないので調整する
        Comparisonにならない式をグルーピング
    """
    def find_comparison(tokens):
        for token in tokens:
            if tu.is_comparison(token):
                return token
        return None

    def adjust_identifier_tokens(comp):
        """
            identifier中のコメントを分解する
        """
        for token in comp.tokens[:]:
            if tu.is_identifier(token):
                for tkn in token.tokens[::-1]:
                    if tkn.is_whitespace() or tu.is_comment(tkn):
                        comp.insert_after(token, tkn)
                        tkn.parent = token
                        token.tokens.remove(tkn)
                    else:
                        break

    def adjust_tokens(tlist, comp_tokens):
        if comp_tokens[0].is_whitespace():
            comp_tokens = comp_tokens[1:]
        if comp_tokens[-1].is_whitespace():
            comp_tokens = comp_tokens[:-1]

        comp = find_comparison(comp_tokens)
        if comp:
            left = True
            left_idx = 0
            for token in comp_tokens:
                if token is comp:
                    left = False
                elif left:
                    comp.insert_before(comp.tokens[left_idx], token)
                    left_idx += 1
                    tlist.tokens.remove(token)
                else:
                    comp.tokens.append(token)
                    tlist.tokens.remove(token)
            adjust_identifier_tokens(comp)
        else:
            if tu.find_comparison_operator_words(comp_tokens):
                tgp = tlist.group_tokens(sql.Comparison, comp_tokens)
                adjust_identifier_tokens(tgp)

    def adjust_prior(tlist, comp_tokens):
        """
            priorの調整
        """
        prior = None
        for token in comp_tokens[:]:
            if not tu.is_enable(token):
                continue

            if prior:
                tokens = tlist.tokens_between(prior, token)
                if tu.is_comparison(token):
                    tgp = token.group_tokens(
                            sql.Identifier,
                            token.tokens_between(token.tokens[0],tu.token_next_enable(token))
                        )
                    for tkn in tokens[1::-1]:
                        tgp.tokens.insert(0, tkn)
                        tkn.parent.tokens.remove(tkn)
                        tkn.parent = tgp
                        comp_tokens.remove(tkn)
                else:
                    idx = comp_tokens.index(prior)
                    comp_tokens.insert(idx, tlist.group_tokens(sql.Identifier, tokens))
                    for tkn in tokens:
                        comp_tokens.remove(tkn)
                prior.ttype = T.Name # Keywordだと改行されてしまうためName属性にする
                prior = None
                continue

            if token.ttype in T.Keyword and tu.equals_ignore_case(token.value, "PRIOR"):
                prior = token
            else:
                prior = None



    def proc(tlist):
        [proc(sgroup) for sgroup in tlist.get_sublists()]

        in_prior = False
        target_tokens = []
        if tu.is_where(tlist):
            where_token = tlist.token_next_match(0, T.Keyword, 'WHERE')
            where_index = tlist.token_index(where_token)
            target_tokens = tlist.tokens[where_index + 1:] # where 以降を処理
        elif tu.is_when(tlist):
            when_token = tlist.token_next_match(0, T.Keyword, 'WHEN')
            when_index = tlist.token_index(when_token)
            target_tokens = tlist.tokens[when_index + 1:] # when 以降を処理
        elif tu.is_having(tlist):
            having_token = tlist.token_next_match(0, T.Keyword, 'HAVING')
            having_index = tlist.token_index(having_token)
            target_tokens = tlist.tokens[having_index + 1:] # having 以降を処理
        elif tu.is_on(tlist):
            on_token = tlist.token_next_match(0, T.Keyword, 'ON')
            on_index = tlist.token_index(on_token)
            target_tokens = tlist.tokens[on_index + 1:] # on 以降を処理
        elif tu.is_connectby(tlist) or tu.is_startwith(tlist):
            in_prior = tu.is_connectby(tlist) # connect byの場合はpriorを考慮
            phrase_token = tlist.token_matching(0, (tu.is_phrase, ))
            phrase_index = tlist.token_index(phrase_token)
            target_tokens = tlist.tokens[phrase_index + 1:] # phrase 以降を処理
        elif tu.is_comparisons_parenthesis(tlist):
            target_tokens = tu.tokens_parenthesis_inner(tlist) # ()の中を処理
        else:
            return

        is_between = False
        comp_tokens = []
        for token in target_tokens: # where/when 以降を処理
            if tu.is_logical_operator_keyword(token):
                if is_between and tu.is_and_keyword(token):
                    is_between = False
                else:
                    if in_prior:
                        adjust_prior(tlist, comp_tokens)
                    adjust_tokens(tlist, comp_tokens)
                    comp_tokens = []
                    continue
            elif tu.is_between_keyword(token):
                is_between = True

            comp_tokens.append(token)
        if comp_tokens:
            if in_prior:
                adjust_prior(tlist, comp_tokens)
            adjust_tokens(tlist, comp_tokens)

    proc = SqlFormatterException.to_wrap_try_except(proc, 0)
    proc(tlist)

def adj_group_identifier_list(stmt, comment_syntax):
    """
        IdentifierListのグルーピングでコメントがあると綺麗に整わないので調整する。
        Oracle方言のIdentifierListの形を調整する
    """

    def within_update_set_section(token):
        if not tu.within_update_set_section(stmt, token):
            return False

        while token.parent:
            parent = token.parent
            if tu.is_parenthesis(parent):
                return False

            if parent.parent:
                if not tu.within_update_set_section(stmt, parent):
                    return True
            else:
                return True
            token = parent


        return True

    def process(tlist):
        def concat_prev(token):
            prev_token = tlist.token_prev(token, skip_ws=False)
            if not prev_token:
                return False
            if tu.is_open_punctuation(prev_token):
                return False
            if tu.is_dml(prev_token):
                return False
            if tu.is_from_keyword(prev_token):
                return False

            if tu.is_identifier_list(prev_token):
                for tkn in prev_token.tokens[::-1]:
                    token.tokens.insert(0, tkn)
            else:
                token.tokens.insert(0, prev_token)
            tlist.tokens.remove(prev_token)
            return True

        def concat_next(token):
            next_token = tlist.token_next(token, skip_ws=False)
            if not next_token:
                return False
            if tu.is_close_punctuation(next_token):
                return False
            if tu.is_from_keyword(next_token):
                return False

            if tu.is_identifier_list(next_token):
                token.tokens.extend(next_token.tokens)
            else:
                token.tokens.append(next_token)
            tlist.tokens.remove(next_token)
            return True

        def is_concat_prev_target(token):
            # 前がAS、演算子で終わっていたら結合
            prev_enable_token = tu.token_prev_enable(tlist, token)
            if prev_enable_token and (\
                ends_with_as_keyword(prev_enable_token) or ends_with_operator(prev_enable_token) \
                ) :
                return True

            # 前がuroboroパラメータコメントで終わっていたら結合
            prev_token = tlist.token_prev(token)
            try:
                if prev_token and tu.is_param_comment(prev_token, next(tu.flatten(token)), comment_syntax) :
                    return True
            except StopIteration:
                pass

            # カンマ、AS、演算子で始まっていたら前を結合
            if starts_with_comma(token) or starts_with_as_keyword(token) or starts_with_operator(token) :
                return True

            return False

        def is_concat_next_target(token):
            # カンマ、AS、演算子で終わっていたら次を結合
            if ends_with_comma(token) or ends_with_as_keyword(token) or ends_with_operator(token) :
                return True

            # 次がカンマ、AS、演算子で始まっていたら結合
            next_enable_token = tu.token_next_enable(tlist, token)
            if next_enable_token \
                    and (
                        starts_with_as_keyword(next_enable_token) \
                        or starts_with_comma(next_enable_token) \
                        or starts_with_operator(next_enable_token) \
                        or starts_with_ascdesc(next_enable_token) \
                    ) :
                return True

            # 次がラインコメントで始まっていたら結合
            next_token = tlist.token_next(token)
            if next_token and (starts_with_line_commecnt(next_token)) :
                return True

            return False

        def proc_identifier_list(token):
            """
                IdentifierListの処理
            """
            change = True
            while change:
                change = False

                while is_concat_prev_target(token) :
                    if not concat_prev(token):
                        break
                    change = True

                while is_concat_next_target(token) :
                    if not concat_next(token):
                        break
                    change = True

            __adjust_identifier_list(token)



        def __adjust_identifier_list(identifier_list):
            """
                カンマ前後の調整
            """
            def adj(tokens):
                lefts = []
                rights = []
                identifier = None
                for i, token in enumerate(tokens):
                    if tu.is_identifier(token) or tu.is_comparison(token):
                        identifier = token
                        rights = tokens[i+1:]
                        lefts = tokens[:i]
                        break

                if identifier:
                    for i, token in enumerate(lefts):
                        identifier.tokens.insert(i, token)
                        token.parent = identifier
                        identifier_list.tokens.remove(token)
                    for token in rights:
                        if not tu.is_identifier(token):
                            identifier.tokens.append(token)
                        else:
                            identifier.tokens.extend(token.tokens)
                        token.parent = identifier
                        identifier_list.tokens.remove(token)
                else:
                    identifier_list.group_tokens(sql.Identifier, tokens)

            idx = 0
            start = identifier_list.tokens[idx]
            comma = identifier_list.token_matching(idx + 1, [tu.is_comma])
            while comma:
                tokens = identifier_list.tokens_between(start, comma, exclude_end = True)

                adj(tokens)

                idx = identifier_list.token_index(comma) + 1
                start = identifier_list.tokens[idx]
                comma = identifier_list.token_matching(idx + 1, [tu.is_comma])

            tokens = identifier_list.tokens_between(start, identifier_list.tokens[-1])
            adj(tokens)

        def ends_with(token, func):
            if token.is_group():
                for token in token.tokens[::-1]:
                    if token.is_whitespace():
                        continue
                    if tu.is_comment(token):
                        continue
                    if token.is_group():
                        return ends_with(token, func)
                    else:
                        return func(token)
                return False
            else:
                return func(token)

        def starts_with(token, func):
            if func(token):
                return True

            if token.is_group():
                for token in token.tokens:
                    if token.is_whitespace():
                        continue
                    if tu.is_comment(token):
                        continue
                    if token.is_group():
                        return starts_with(token, func)
                    else:
                        return func(token)

            return False

        def ends_with_comma(token):
            return ends_with(token, tu.is_comma)

        def starts_with_comma(token):
            return starts_with(token, tu.is_comma)

        def ends_with_as_keyword(token):
            return ends_with(token, tu.is_as_keyword)

        def starts_with_as_keyword(token):
            return starts_with(token, tu.is_as_keyword)

        def ends_with_operator(token):
            if not within_update_set_section(token):
                # UPDATE句でなければ比較演算子は含まない
                return ends_with(token, lambda t: tu.is_operator(t) and not tu.is_comparison_operator(t))
            else:
                # UPDATE句なら比較演算子も含む
                return ends_with(token, tu.is_operator)

        def starts_with_operator(token):
            if not within_update_set_section(token):
                # UPDATE句でなければ比較演算子は含まない
                return starts_with(token, lambda t: tu.is_operator(t) and not tu.is_comparison_operator(t))
            else:
                # UPDATE句なら比較演算子も含む
                return starts_with(token, tu.is_operator)

        def starts_with_ascdesc(token):
            return starts_with(token, lambda t: isinstance(t, AscDesc))

        def starts_with_line_commecnt(token):
            return starts_with(token, tu.is_line_comment)


        [process(sgroup) for sgroup in tlist.get_sublists()]
        i = 0
        while len(tlist.tokens) > i + 1:
            token = tlist.tokens[i]
            tgt = token
            if tu.is_identifier_list(token):
                proc_identifier_list(token)
            elif tu.is_identifier(token) \
                    and (not tu.is_function(token.parent)) \
                    and (not tu.is_identifier_list(token.parent)) \
                    and (not tu.is_identifier(token.parent)) \
                    and (not tu.is_comparison(token.parent)):
                # 次がAS等で始まっていたらIdentifierList化して調整
                if is_concat_next_target(token) or is_concat_prev_target(token):
                    grp = tlist.group_tokens(sql.IdentifierList, [token])
                    proc_identifier_list(grp)
                    tgt = grp
            elif (tu.is_literal(token) or tu.is_parenthesis(token)) \
                    and (not tu.is_function(token.parent)) \
                    and (not tu.is_identifier_list(token.parent)) \
                    and (not tu.is_identifier(token.parent)) \
                    and (not tu.is_comparison(token.parent)):
                # リテラル、()の時、
                # 次がカンマならIdentifier→IdentifierList化。UPDATE句で次が比較演算子ならIdentifier→IdentifierList化。
                next_token = tu.token_next_enable(tlist, token)
                if next_token \
                        and (
                            tu.is_comma(next_token) \
                            or (within_update_set_section(token) and tu.is_comparison_operator(next_token))
                        ):
                    identifier = tlist.group_tokens(sql.Identifier, [token])
                    grp = tlist.group_tokens(sql.IdentifierList, [identifier])
                    proc_identifier_list(grp)
                    tgt = grp

            i = tlist.token_index(tgt) + 1

    process = SqlFormatterException.to_wrap_try_except(process, 0)
    process(stmt)

def re_group(tlist):
    for func in [
            re_group_tree, # group_aliasedで親子関係が正しくならないので修正
            re_group_comment,
            re_group_parenthesis,
            re_group_function,
            re_group_case,
            ]:
        func(tlist)

def group(tlist):
    for func in [
            re_group_tree,

            # グルーピングで崩れる前に処理する
            group_having,

            GroupingCalculation().process,
            GroupingWithinGroupFunctions().process,
            GroupingPhrase().process,
            GroupingAscDesc().process,
            GroupingOffsetFetch().process,
            GroupingLimitOffset().process,

            # OVERの処理に影響するのでこのタイミングで処理
            AdjustGroupingFunction().process,

            GroupingOverFunctions().process,
            GroupingKeepFunctions().process,
            GroupingWaitOrNowait().process,
            GroupingForUpdate().process,
            GroupingUnion().process,
            GroupingJoin().process,
            GroupingMergeWhen().process,
            GroupingWith().process,
            GroupingSpecialFunctionParameter().process,
            group_on,
            group_when,
            group_mergeupdateinsertclause,
            group_connectby_startwith,
            ]:
        func(tlist)

def adj_group(tlist, comment_syntax):
    for func in [
            # AdjustGroupingFunction().process,
            adj_group_comparison,
            lambda t: adj_group_identifier_list(t, comment_syntax),
            ]:
        func(tlist)
