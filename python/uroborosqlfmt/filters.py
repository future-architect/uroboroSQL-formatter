# coding:utf-8
'''
@author: ota
'''
import math
import re
import sys
from sqlparse import sql, tokens as T, utils
from sqlparse.filters import StripWhitespaceFilter, ReindentFilter
from uroborosqlfmt import tokenutils as tu, grouping
from uroborosqlfmt.exceptions import SqlFormatterException
from uroborosqlfmt.sql import Phrase


class StripWhitespaceAndToTabFilter(StripWhitespaceFilter):
    """
        連続したwhitespaceを除去し、
        Punctuation前後のwhitespaceも除去する
        またwhitespaceはTab文字で統一する
    """
    def process(self, stack, stmt, depth=0):
        SqlFormatterException.wrap_try_except(
                super(StripWhitespaceAndToTabFilter, self).process,
                stmt,
                stack,
                stmt,
                depth
            )

    def __custom_stripws_tokenlist(self, tlist):
        """
            コメントとラインコメントの間のスペースを除去
        """
        last_token = None
        ws_tokens = []
        for token in tlist.tokens[:]:

            if tu.is_line_comment(token) and last_token and tu.is_comment(last_token):
                for tws in ws_tokens:
                    tlist.tokens.remove(tws)

                last_token = token
                ws_tokens = []
            elif token.is_whitespace():
                ws_tokens.append(token)
            else:
                last_token = token
                ws_tokens = []


    def _stripws_default(self, tlist):
        last_was_ws = False
        last_ws_token = None
        last_was_punctuation = False
        for token in tlist.tokens[:]:
            if token.is_whitespace():
                if last_was_ws or last_was_punctuation:  # 前tokenがwhitespaceまたはPunctuationの場合、空白を除去
                    tlist.tokens.remove(token)
                    continue
                else:
                    token.value = "\t"
            if tu.is_punctuation(token):
                if last_ws_token:
                    tlist.tokens.remove(last_ws_token) # Punctuation前のwhitespaceを除去
            last_was_ws = token.is_whitespace()
            last_ws_token = token if last_was_ws else None
            last_was_punctuation = tu.is_punctuation(token)

        self.__custom_stripws_tokenlist(tlist)


    def _stripws_identifierlist(self, tlist):
        super(StripWhitespaceAndToTabFilter, self)._stripws_identifierlist(tlist)

        self.__custom_stripws_tokenlist(tlist)

    def _stripws_parenthesis(self, tlist):
        super(StripWhitespaceAndToTabFilter, self)._stripws_parenthesis(tlist)

        self.__custom_stripws_tokenlist(tlist)

class GroupFilter(object):
    """
        グルーピング関連
    """

    def process(self, _, stmt):
        grouping.re_group(stmt)
        grouping.group(stmt)


class LineDescriptionLineCommentFilter(object):
    """
        ラインコメント行の説明を成しているか、次の説明を成しているか振り分ける
    """

    class Comment(sql.Comment):
        """
            置き換え用コメントクラスのラッパー
        """
        __slots__ = ('is_line_description')

    def __init__(self, local_config):
        self.local_config = local_config
        self.is_line_description = False

    def process(self, _, stmt):
        def custom_flaten(token):
            """
                コメントはflatenしないflaten
            """
            if isinstance(token, sql.TokenList) and not tu.is_comment(token):
                for tkn in token.tokens:
                    for item in custom_flaten(tkn):
                        yield item
            else:
                yield token
        is_prev_cr = True
        for token in custom_flaten(stmt):
            if tu.is_plain_line_comment(token, self.local_config.comment_syntax):
                # コメントクラス置き換え
                parent = token.parent
                index = parent.tokens.index(token)
                comment = LineDescriptionLineCommentFilter.Comment(token.tokens)
                for tkn in token.tokens:
                    tkn.parent = comment
                comment.parent = parent
                parent.tokens[index] = comment
                # フラグセット
                comment.is_line_description = not is_prev_cr # pylint: disable=attribute-defined-outside-init
            elif token.is_whitespace():
                if is_inc_cr(token):
                    is_prev_cr = True
            else:
                is_prev_cr = False



class AdjustGroupFilter(object):
    """
        グルーピング調整
    """

    def __init__(self, local_config):
        self.comment_syntax = local_config.comment_syntax


    def process(self, _, stmt):
        grouping.adj_group(stmt, self.comment_syntax)


class _LineObject(object):
    def _rstrip(self, target_tokens, base_token):
        for tkn in target_tokens[::-1]:
            if tkn.is_whitespace():
                base_token.tokens.remove(tkn)
                target_tokens.remove(tkn)
            else:
                break
    def _remove_indent(self, lines, indent):
        for i, line in enumerate(lines):
            for cval in line[:indent]:
                if cval == "\t":
                    lines[i] = lines[i][1:]
                else:
                    break

    def _right_tokens_between(self, base_token, separetor, line_comment):
        start = base_token.token_next(separetor) if separetor else base_token.tokens[0]

        if not line_comment:
            return base_token.tokens_between(start, base_token.tokens[-1])
        else:
            return base_token.tokens_between(start, line_comment, exclude_end=True)

    def _get_linecomment(self, base_token, comment_syntax):
        first_line_comment = None
        for tkn in base_token.tokens[::-1]:
            if tu.is_line_description_line_comment(tkn, comment_syntax):
                first_line_comment = tkn
                continue
            if tkn.is_whitespace():
                continue
            if tu.is_comment(tkn):
                continue
            return first_line_comment
        return None

class _BaseIdentifierObject(_LineObject):
    """
        Identifier内部のインデント調整用のObject
    """

    def __init__(self, token, indent, local_config):
        self.token = token
        self.center_token = None
        self.line_comment = None
        self.left_tokens = []
        self.right_tokens = []

        self.left_lines = []
        self.right_lines = []

        self.width_left = 0
        self.width_right = 0

        self.line_comment = self._get_linecomment(token, local_config.comment_syntax)

        separetor = self._get_separetor_token(token)

        if separetor:
            self.center_token = self._get_center_token(token)

            self.left_tokens = token.tokens_between(token.tokens[0], separetor, exclude_end=True)
            self.right_tokens = self._right_tokens_between(token, separetor, self.line_comment)


            self._rstrip(self.left_tokens, token)
            self._rstrip(self.right_tokens, token)

            lefts = utils.split_unquoted_newlines("".join([str(t) for t in self.left_tokens]))
            rights = utils.split_unquoted_newlines("".join([str(t) for t in self.right_tokens]))

            self._remove_indent(lefts, indent)
            self._remove_indent(rights, indent)

            self.width_left = get_need_tab_char_width(lefts[-1])
            self.width_right = get_need_tab_char_width(rights[-1])
            self.left_lines = lefts
            self.right_lines = rights
        else:
            self.left_tokens = self._right_tokens_between(token, None, self.line_comment)

            self._rstrip(self.left_tokens, token)

            lefts = utils.split_unquoted_newlines("".join([str(t) for t in self.left_tokens]))

            self._remove_indent(lefts, indent)

            self.width_left = get_need_tab_char_width(lefts[-1])
            self.left_lines = lefts

    def _get_center_token(self, token):
        pass
    def _get_separetor_token(self, token):
        pass

    def __str__(self, *args, **kwargs):
        left = "".join(str(t) for t in self.left_tokens)
        right = "".join(str(t) for t in self.right_tokens)
        comment = str(self.line_comment)


        return "left:" + left + "\nright:" + right + "\ncomment:" + comment

class _IdentifierObject(_BaseIdentifierObject):

    def _get_separetor_token(self, token):
        alias = self._get_alias(token)
        if alias:
            as_token = token.token_next_match(0, T.Keyword, "AS")
            if as_token:
                return as_token
            else:
                return token.token_prev(alias, skip_ws=False)

        return None

    def _get_center_token(self, token):
        return token.token_next_match(0, T.Keyword, "AS")


    def _get_alias(self, token):
        tkw = token.token_next_match(0, T.Keyword, 'AS')
        if tkw is not None:
            return tu.token_next_enable(token, tkw)

        left = tu.token_next_enable(token)
        if not left:
            return None

        def is_space(tkn):
            return tkn.is_whitespace() and tkn.value

        spl = token.token_matching(token.token_index(left), [is_space])
        if spl:
            return tu.token_next_enable(token, spl)

        if tu.is_parenthesis(left):
            tkn = tu.token_next_enable(token, left)
            if tkn and (tu.is_identifier(tkn) or (tkn.ttype in T.Name)):
                # (・・・)ALIAS の場合
                space = sql.Token(T.Whitespace, "\t") # スペースを付与
                token.insert_after(left, space)
                return tkn

        return None

class _UpdIdentifierObject(_BaseIdentifierObject):

    def _get_separetor_token(self, token):
        comp = token.token_next_match(0, T.Comparison, "=")
        if comp:
            return comp
        else:
            second = tu.token_next_enable(token, tu.token_next_enable(token))
            return token.token_prev(second, skip_ws=False)

        return None

    def _get_center_token(self, token):
        return token.token_next_match(0, T.Comparison, "=")



class _ComparisonObject(_LineObject):
    """
        Comparison内部のインデント調整用のObject
    """

    def __init__(self, token, indent, local_config):
        self.token = token

        self.line_comment = None
        self.left_tokens = []
        self.right_tokens = []
        self.operator_tokens = []

        self.left_lines = []
        self.right_lines = []
        self.operator_string = ""

        self.width_left = 0
        self.width_right = 0

        self.line_comment = self._get_linecomment(token, local_config.comment_syntax)

        op_tokens = tu.find_comparison_operator_words(token.tokens)
        if len(op_tokens) > 1:
            self.operator_tokens = token.tokens_between(op_tokens[0], op_tokens[1])
            for tkn in self.operator_tokens[1:-1]:
                if tkn.is_whitespace():
                    tkn.value = " "
        else:
            self.operator_tokens = op_tokens

        for tkn in self.operator_tokens:
            if tkn.is_whitespace():
                tkn.value = " "
        self.operator_string = "".join(str(tkn) for tkn in self.operator_tokens)

        tws = token.token_next(self.operator_tokens[-1], skip_ws=False)
        if tws.is_whitespace():
            # 比較演算の隣の空白を削除
            token.tokens.remove(tws)


        self.left_tokens = token.tokens_between(token.tokens[0], self.operator_tokens[0], exclude_end=True)
        self.right_tokens = self._right_tokens_between(token, self.operator_tokens[-1], self.line_comment)

        self._rstrip(self.left_tokens, token)
        self._rstrip(self.right_tokens, token)

        lefts = utils.split_unquoted_newlines("".join([str(tkn) for tkn in self.left_tokens]))
        rights = utils.split_unquoted_newlines("".join([str(tkn) for tkn in self.right_tokens]))

        self._remove_indent(lefts, indent)
        self._remove_indent(rights, indent)

        self.width_left = get_need_tab_char_width(lefts[-1])
        self.width_right = get_need_tab_char_width(rights[-1])
        self.width_operator = get_need_tab_char_width(self.operator_string)
        self.left_lines = lefts
        self.right_lines = rights

    def __str__(self, *args, **kwargs):
        left = "".join(str(t) for t in self.left_tokens)
        right = "".join(str(t) for t in self.right_tokens)
        comment = str(self.line_comment)
        operator = str(self.operator_string)


        return "left:" + left + "\noperator:" + operator + "\nright:" + right + "\ncomment:" + comment

class OperatorFilter(object):
    """
        比較演算子の統一
    """
    def __init__(self):
        self._process = SqlFormatterException.to_wrap_try_except(self._process, 0)

    def process(self, _, stmt):
        self._process(stmt)

    def _process(self, tlist): # pylint: disable=method-hidden
        [self._process(sgroup) for sgroup in tlist.get_sublists()]

        for token in tlist.tokens:
            if tu.is_operator(token) and token.value in ("<>", "^="):
                token.value = "!="

class MoveCommaFilter(object):
    """
        カンマ位置調整
    """
    def __init__(self, local_config):
        self._process = SqlFormatterException.to_wrap_try_except(self._process, 0)
        self.local_config = local_config

    def process(self, _, stmt):
        self._process(stmt, [])

    def _process(self, tlist, parents): # pylint: disable=method-hidden
        tps = [tlist] + parents
        [self._process(sgroup, tps) for sgroup in tlist.get_sublists()]
        for token in tlist.tokens[:]:
            if tu.is_comma(token):
                nxt = tlist.token_next(token)
                if nxt:
                    prv = tlist.token_prev(token)
                    comment = hit_first(
                            nxt,
                            lambda t: tu.is_line_description_line_comment(t, self.local_config.comment_syntax)
                        )
                    if comment and not (prv \
                            and hit_last(
                                    prv,
                                    lambda t: tu.is_line_description_line_comment(t, self.local_config.comment_syntax)
                                )
                        ):
                        self.__move_token(tlist, token, comment)

    def __move_token(self, parent, token_a, token_b):
        if token_b in parent.tokens:
            idxa = parent.tokens.index(token_a)
            idxb = parent.tokens.index(token_b)
            parent.tokens[idxa] = token_b
            parent.tokens[idxb] = token_a
        else:
            def remove_token(parent, token):
                if token in parent.tokens:
                    parent.tokens.remove(token)
                    return True
                else:
                    for tkn in parent.tokens:
                        if tkn.is_group() and remove_token(tkn, token):
                            return True
                    return False
            remove_token(parent, token_b)

            parent.insert_before(token_a, token_b)
            token_b.parent = parent



class CustomReindentFilter(ReindentFilter):
    """
        インデント処理
    """

    def __init__(self, local_config):
        super(CustomReindentFilter, self).__init__(1, "\t")
        self.local_config = local_config

    def process(self, stack, stmt):
        super(CustomReindentFilter, self).process(stack, stmt)


        flatten = list(tu.flatten(stmt))

        if not flatten:
            return

        if tu.is_semicolon_punctuation(flatten[-1]):
            tcr = self.cr()
            flatten[-1].parent.insert_before(flatten[-1], tcr)
            flatten = flatten[:-1] + [tcr] + flatten[-1:]

        # 重複した改行を削除

        # まずは空白を結合
        pre = flatten[0]
        for token in flatten[1:]:
            if token.is_whitespace():
                if pre.is_whitespace():
                    pre.value += token.value
                    token.value = ""
                    continue
            pre = token

        # 重複した改行の除去
        pre = None
        for token in flatten:
            if token.is_whitespace():
                text = str(token)
                if not text:
                    continue

                white_lines = utils.split_unquoted_newlines(str(token))
                while len(white_lines) > 2:
                    del white_lines[1]

                if pre:
                    if len(white_lines) > 1 and pre.parent and tu.is_line_comment(pre.parent):
                        # 行コメントの後なら自分の改行を除去
                        del white_lines[0]
                else:
                    if len(white_lines) > 1:
                        # 最初の改行を削除
                        del white_lines[0]

                token.value = "\n".join(white_lines)

            pre = token

    def _process(self, tlist):
        SqlFormatterException.wrap_try_except(super(CustomReindentFilter, self)._process, tlist)

    def __within_with_section(self, token):
        return tu.within_with_section(self._curr_stmt, token)

    def __within_select_statement(self, token):
        return tu.within_select_statement(self._curr_stmt, token)

    def __within_insert_statement(self, token):
        return tu.within_insert_statement(self._curr_stmt, token)

    def __within_merge_statement(self, token):
        return tu.within_merge_statement(self._curr_stmt, token)

    def __within_update_statement(self, token):
        return tu.within_update_statement(self._curr_stmt, token)

    def __within_update_set_section(self, token):
        return tu.within_update_set_section(self._curr_stmt, token)

    def __within_insert_values_section(self, token):
        return tu.within_insert_values_section(self._curr_stmt, token)

    def __within_insert_into_columns_section(self, token):
        return tu.within_insert_into_columns_section(self._curr_stmt, token)

    def __custom_process_list(self, tlist):
        for token in tlist.tokens[:]:
            if tu.is_dml(token):
                tlist.insert_before(token, self.nl())
                tlist.insert_after(token, self.nl())
            elif tu.is_from_keyword(token):
                tlist.insert_before(token, self.nl()) # DELETEの場合（？）_split_kwdsで戻されてしまうため2つ改行する
                tlist.insert_before(token, self.nl())
                tlist.insert_after(token, self.cr())
            elif tu.is_wildcard(token) or tu.is_literal(token) or tu.is_function(token):
                prev = tlist.token_prev(token, skip_ws=False)
                if prev and tu.is_param_comment(prev, token, self.local_config.comment_syntax):
                    target = prev
                else:
                    target = token

                prev = tu.token_prev_enable(tlist, target)
                if prev and hit_last(prev, tu.is_dml):
                    tlist.insert_before(target, self.nl_with_indent(1))
                else:
                    tlist.insert_before(target, self.indent_space())
            elif tu.is_identifier(token) or tu.is_parenthesis(token):
                prev = tu.token_prev_enable(tlist, token)
                def is_need_indent(tkn):
                    if tu.is_from_keyword(tkn):
                        return True
                    if tu.is_by_keyword(tkn):
                        return True
                    if tu.is_select_dml(tkn):
                        return True
                    if tu.is_update_dml(tkn):
                        return True

                    if tu.is_into_keyword(tkn) and (
                            self.__within_insert_statement(tkn) \
                            or self.__within_merge_statement(tkn)
                        ):
                        return True
                    if tu.is_using_keyword(tkn) and self.__within_merge_statement(tkn):
                        return True

                    if tu.is_set_keyword(tkn) and self.__within_update_statement(tkn):
                        return True

                    return False

                if prev and hit_last(prev, is_need_indent):
                    self.offset += 1
                    self.__custom_process_identifier(tlist, token)
                    self.offset -= 1
                else:
                    self.__custom_process_identifier(tlist, token)

            elif tu.is_distinct_keyword(token):
                tlist.insert_before(token, self.nl_with_indent(1))
            elif tu.is_into_keyword(token) and (
                    self.__within_insert_statement(token) \
                    or self.__within_merge_statement(token)
                ):
                tlist.insert_before(token, self.nl())
            elif tu.is_using_keyword(token) and self.__within_merge_statement(token):
                tlist.insert_before(token, self.nl())
            elif tu.is_keyword(token) and tu.endswith_ignore_case(token.value, "COUNT"): # 念のため現状はCOUNTのみ処理
                # keyword として扱われたidentifierを処理
                prev = tu.token_prev_enable(tlist, token)
                def is_need_indent(tkn):
                    if tu.is_from_keyword(tkn):
                        return True
                    if tu.is_by_keyword(tkn):
                        return True
                    if tu.is_select_dml(tkn):
                        return True
                    if tu.is_update_dml(tkn):
                        return True

                    if tu.is_into_keyword(tkn) and (
                            self.__within_insert_statement(tkn) \
                            or self.__within_merge_statement(tkn)
                        ):
                        return True
                    if tu.is_using_keyword(tkn) and self.__within_merge_statement(tkn):
                        return True

                    if tu.is_set_keyword(tkn) and self.__within_update_statement(tkn):
                        return True

                    return False

                if prev and hit_last(prev, is_need_indent):
                    self.offset += 1
                    tlist.insert_before(token, self.nl())
                    self.offset -= 1


    def __custom_process_identifier(self, parent, identifier):
        parent.insert_before(identifier, self.nl())
        # 一つだけなら改行＋インデント要らない
#         if tu.is_line_comment(identifier.tokens[-1]):
#             identifier.tokens[-1].tokens[-1].value = identifier.tokens[-1].tokens[-1].value.rstrip("\t")
#         else:
#             parent.insert_after(identifier, self.nl_with_indent(-1))

    def __custom_process_line_comment(self, comment):
        tcm = comment.token_next_by_type(0, T.Comment)
        text = tcm.value[2:]
        text = text.strip()
        tcm.value = "-- " + text + "\n"

    def __custom_process_block_comment(self, comment, is_hint):
        start = comment.token_matching(0, [lambda t: t.ttype in T.Comment and t.value == "/*"])
        end = comment.token_matching(
                comment.token_index(start) + 1,
                [lambda t: t.ttype in T.Comment and t.value == "*/"]
            )

        tokens = comment.tokens_between(start, end)[1:-1]
        if not tokens:
            return

        comment.insert_before(comment.tokens[0], self.nl())

        text_token = tokens[0]
        while len(tokens) > 1:
            # コメントのノードが分かれていたら1つに結合する
            tgt = tokens[1]
            text_token.value += tgt.value
            comment.tokens.remove(tgt)
            tokens.remove(tgt)
        if is_hint:
            text_token.value = text_token.value[1:] # 一旦+を抜く

        text = str(text_token)
        lines = utils.split_unquoted_newlines(text)

        def is_doc_comment(lines):
            """
                /*
                 * この形式のコメントかどうか？
                 */
            """
            end = len(lines) if lines[-1].strip() else -1
            tgtlines = lines[1:end]
            if not tgtlines:
                return False
            for line in tgtlines:
                if not line.lstrip().startswith("*"):
                    return False
            return True

        def is_separator_line_comment(lines):
            """
                /******************/
            """
            return len(lines) == 1 and lines[0] == ("*"  * len(lines[0]))

        def is_lines_doc_comment(lines):
            """
                /******************
                    この形式のコメント
                ****************/
            """
            if len(lines) < 2:
                return False
            fst = lines[0].strip()
            if (not fst) or (fst != ("*"  * len(fst))):
                return False
            lst = lines[-1].strip()
            if (not lst) or (lst != ("*"  * len(lst))):
                return False
            return True

        def remove_blank_lines(lines):
            # 前後の空行削除
            while not lines[0].strip():
                del lines[0]
            while not lines[-1].strip():
                del lines[-1]

        def format_doc(lines):
            remove_blank_lines(lines)

            for i, value in enumerate(lines):
                text = value.lstrip()
                if not text.startswith("*"):
                    text = "* " + text
                elif not text.startswith("* "):
                    text = text[0] + " "  + text[1:]
                lines[i] = str(self.indent_space()) + " " + text

            lines += [str(self.indent_space()) + " "]

            return "\n" + "\n".join(lines)

        def format_hint(lines):
            # hint句なら+を戻す
            return "+" + format_normal(lines)

        def format_normal(lines):
            remove_blank_lines(lines)

            for i, value in enumerate(lines):
                lines[i] = str(self.indent_space(1)) + value.lstrip()

            lines += [str(self.indent_space())]

            return "\n" + "\n".join(lines)

        def format_oneline(lines):
            return "".join(lines)

        def format_lines_doc(lines):
            for i, value in enumerate(lines[:-1]):
                if i:
                    lines[i] = str(self.indent_space(1)) + value.lstrip()
            lines[-1] = str(self.indent_space()) + lines[-1].strip()

            lines[0] = lines[0].lstrip()

            return "\n".join(lines)

        if is_doc_comment(lines):
            text_token.value = format_doc(lines)
        elif is_hint:
            text_token.value = format_hint(lines)
        elif is_separator_line_comment(lines):
            text_token.value = format_oneline(lines)
        elif is_lines_doc_comment(lines):
            text_token.value = format_lines_doc(lines)
        else:
            text_token.value = format_normal(lines)

        comment.insert_after(comment.tokens[-1], self.nl())

    def __custom_process_inorder_function(self, function):
        name_token = tu.token_next_enable(function)

        parenthesis = tu.token_next_enable(function, name_token)

        spaces = function.tokens_between(name_token, parenthesis)[1:-1]
        for tkn in spaces:
            if tkn.is_whitespace():
                function.tokens.remove(tkn)

        self.__custom_process_parenthesis_order(parenthesis)

    def __custom_process_parenthesis_order(self, parenthesis):
        open_punc = parenthesis.token_next_match(0, T.Punctuation, '(')
        close_punc = parenthesis.token_next_match(open_punc, T.Punctuation, ')')

        self.indent += 2
        parenthesis.insert_after(open_punc, self.nl())

        for token in parenthesis.tokens_between(open_punc, close_punc)[1:-1]:
            if isinstance(token, Phrase):
                parenthesis.insert_before(token, self.nl())
                self._process_phrase(token, kwds=False)
                parenthesis.insert_after(token, self.nl_with_indent(1))
            elif isinstance(token, sql.Identifier) and len(token.tokens)==1 and isinstance(token.tokens[0], Phrase):
                # 中がPhraseのIdentifier
                child_token = token.tokens[0]
                parenthesis.insert_before(token, self.nl())
                self._process_phrase(child_token, kwds=False)
                parenthesis.insert_after(token, self.nl_with_indent(1))
            elif token.is_group():
                self._process(token)

        self.indent -= 1
        parenthesis.insert_before(close_punc, self.nl())
        self.indent -= 1

    def __custom_process_insert_values_lr(self, tlist):
        #INSERT の場合VALUES前後に空白1つをセット
        values_token = tlist.token_next_match(0, T.Keyword, "VALUES")
        if values_token:
            prv = tlist.token_prev(values_token, skip_ws=False)
            if prv and prv.is_whitespace():
                prv.value = " "
                prv = tlist.token_prev(prv, skip_ws=False)
                while prv and prv.is_whitespace():
                    prv.value = ""
                    prv = tlist.token_prev(prv, skip_ws=False)
            else:
                tlist.insert_before(values_token, sql.Token(T.Whitespace, " "))

            nxt = tlist.token_next(values_token, skip_ws=False)
            if nxt and nxt.is_whitespace():
                nxt.value = " "
                nxt = tlist.token_next(nxt, skip_ws=False)
                while nxt and nxt.is_whitespace():
                    nxt.value = ""
                    nxt = tlist.token_next(nxt, skip_ws=False)
            else:
                tlist.insert_after(values_token, sql.Token(T.Whitespace, " "))


    def _process_statement(self, tlist):
        self.__custom_process_list(tlist)
        self._process_default(tlist)

        tkn = tu.token_next_enable(tlist)
        if tkn and tu.is_insert_dml(tkn):
            self.__custom_process_insert_values_lr(tlist)


    def _process_comment(self, tlist):
        if tu.is_block_comment(tlist):
            usql = tu.get_comment_type(tlist, self.local_config.comment_syntax)
            if usql == tu.EngineComment.param:
                pass
            elif usql == tu.EngineComment.syntax:
                tlist.insert_before(tlist.tokens[0], self.nl())
                tlist.insert_after(tlist.tokens[-1], self.nl())
            elif usql == tu.EngineComment.sql_identifier:
                # 前の改行を削除。半角スペース開ける
                whitespaces = []
                for tkn in self._flatten_tokens_prev(tlist):
                    if tkn.is_whitespace():
                        whitespaces.append(tkn)
                    else:
                        break
                if whitespaces:
                    whitespaces[-1].value = " "
                    for tws in whitespaces[:-1]:
                        tws.value = ""
                tlist.insert_after(tlist.tokens[-1], self.nl())
            elif tu.is_hint_block_comment(tlist):
                self.__custom_process_block_comment(tlist, True)
            else:
                self.__custom_process_block_comment(tlist, False)

        elif tu.is_line_comment(tlist):
            self.__custom_process_line_comment(tlist)
            for tkn in tlist.tokens[:]:
                if tkn.is_whitespace():
                    tlist.tokens.remove(tkn)

            usql = tu.get_comment_type(tlist, self.local_config.comment_syntax)
            if usql != tu.EngineComment.none:
                # Uroboroシンタックスのラインコメントなので改行を入れる
                tlist.insert_before(tlist.tokens[0], self.nl())
            elif not tu.is_line_description_line_comment(tlist, self.local_config.comment_syntax):
                # もともと改行後のラインコメントだったので改行を入れる
                tlist.insert_before(tlist.tokens[0], self.nl())

            tlist.insert_after(tlist.tokens[-1], self.nl())

        self._process_default(tlist)

    def _process_identifierlist(self, tlist):
        self._process_default(tlist)

        if not self._is_format_target_identifire_list(tlist):
            return

        identifiers = list(tlist.get_identifiers())
        self._adjust_identifiers_indent(identifiers)

        if identifiers:
            self.offset += 1
            first = identifiers[0]
            tlist.insert_before(first, self.nl())
            tlist.insert_after(first, self.nl_with_indent(-1))
            if len(identifiers) > 1:
                for token in identifiers[1:-1]:
                    tlist.insert_before(token, self.one_indent_space())
                    tlist.insert_after(token, self.nl_with_indent(-1))
                last = identifiers[-1]
                tlist.insert_before(last, self.one_indent_space())
            self.offset -= 1

    def _process_when(self, tlist):
        token = tlist.token_next_match(0, T.Keyword, 'WHEN')
        try:
            tlist.insert_before(token, self.nl())
            tlist.insert_after(token, self.nl_with_indent(1))
        except ValueError:  # issue121, errors in statement
            pass

        self._process_default(tlist)
        self._adjust_comparisons_indent(self._get_comparisons(tlist))

    def _process_where(self, tlist):
        token = tlist.token_next_match(0, T.Keyword, 'WHERE')
        try:
            tlist.insert_before(token, self.nl())
            tlist.insert_after(token, self.nl_with_indent(1))
        except ValueError:  # issue121, errors in statement
            pass

        self._process_default(tlist)
        self._adjust_comparisons_indent(self._get_comparisons(tlist))

    def _process_having(self, tlist):
        self._process_default(tlist)

        token = tlist.token_next_match(0, T.Keyword, 'HAVING')
        try:
            tlist.insert_before(token, self.nl())
            tlist.insert_after(token, self.nl_with_indent(1))
        except ValueError:  # issue121, errors in statement
            pass

        self._adjust_comparisons_indent(self._get_comparisons(tlist))

    def _process_comparison(self, tlist):
#         tlist.insert_before(tlist.tokens[0], self.indent_space(1))
        self._process_default(tlist)

    def _process_parenthesis(self, tlist):

        def is_insert_parenthesis(tlist):
            if not self.__within_insert_statement(tlist):
                return False
            if self.__within_insert_values_section(tlist): # insertのvaluesの処理
                return True

            if self.__within_insert_into_columns_section(tlist): # insertのinto columnsの処理
                return True

            return False

        def is_include_join(tlist):
            token = tu.tokens_parenthesis_inner(tlist)
            for tkn in token:
                if tu.is_join(tkn):
                    return True

            return False

        def is_with_query_cols(tlist):
            """
                WITHのqueryカラム名括弧判定
            """
            parent = tlist.parent
            if parent and tu.is_identifier(parent):
                nametoken = tu.token_prev_enable(parent, tlist)
                if not nametoken:
                    return False
                if not tu.is_identifier(nametoken) and not nametoken.ttype in T.Name:
                    return False

                parent = parent.parent
                if parent and tu.is_identifier_list(parent):
                    parent = parent.parent
                    if parent and tu.is_with(parent):
                        return True
            return False

        def is_need_shift(tlist):
            """
                閉じ括弧「)」の前が改行されている場合shiftさせる
                ただし開き括弧「(」の前が改行されている場合はshiftさせない
            """
            # 開き括弧「(」の前が改行されているかどうか？
            open_punc = tlist.token_next_match(0, T.Punctuation, '(')
            exists = False
            spaces = ""
            for token in self._flatten_tokens_prev(open_punc):
                exists = True
                if token.is_whitespace():
                    spaces += token.value
                    if is_inc_cr(token):
                        if spaces.count("\tkn") == self.indent:
                            return False
                        # 閉じ括弧判定へ
                        break
                else:
                    # 閉じ括弧判定へ
                    break
            if not exists:
                return False


            # 閉じ括弧「)」の前が改行されているかどうか？
            close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
            for tkn in tlist.tokens_between(open_punc, close_punc)[1::-1]:
                for token in list(tu.flatten(tkn))[::-1]:
                    if token.is_whitespace():
                        if is_inc_cr(token):
                            return True
                    else:
                        return False
            return False

        if tu.is_dmlddl_parenthesis(tlist): # 括弧の中はDML
            self.__process_parenthesis_for_dmlddl(tlist)
        elif tu.is_comparisons_parenthesis(tlist): # 条件の括弧
            self.__process_parenthesis_for_complist(tlist)
        elif is_insert_parenthesis(tlist): # INSERT句の括弧
            self.__process_parenthesis_for_insert(tlist)
        elif is_include_join(tlist): # JOIN句の括弧
            self.__process_parenthesis_for_jointables(tlist)
        elif is_with_query_cols(tlist): # WITH句の括弧
            self.__process_parenthesis_for_with_query_cols(tlist)
        elif tu.is_enum_parenthesis(tlist):
            if self._is_include_format_target_identifire_list_parenthesis(tlist):
                self.__process_parenthesis_for_identifier_list(tlist) # identifierlistのフォーマットを期待した処理
            else:
                self.__process_parenthesis_for_enum(tlist) # 値の列挙ならカンマ後のスペースだけ処理
        else:
            self._process_default(tlist, stmts=True)

            # 閉じ括弧「)」の前が改行されている場合右にshiftさせる（中身をIndentする）
            if is_need_shift(tlist):
                self.__indent_shift(tlist)

    def __process_parenthesis_for_identifier_list(self, tlist):
        open_punc = tlist.token_next_match(0, T.Punctuation, '(')
        self.indent += 1
        tlist.insert_after(open_punc, self.nl_with_indent(1))
        self._process_default(tlist)

        close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
        tlist.insert_before(close_punc, self.nl())

        self.indent -= 1

    def __process_parenthesis_for_enum(self, parenthesis):
        def proc_parenthesis(tokens, parent):
            for token in tokens:
                if tu.is_comma(token):
                    next_token = parent.token_next(token, skip_ws=False)
                    if next_token and next_token.is_whitespace():
                        next_token.value = " "
                    else:
                        parent.insert_after(token, sql.Token(T.Whitespace, " "))
                elif tu.is_identifier_list(token):
                    proc_parenthesis(token.tokens[:], token)
                elif token.is_group():
                    self._process(token)

        proc_parenthesis(tu.tokens_parenthesis_inner(parenthesis), parenthesis)

    def __process_parenthesis_for_join_using(self, tlist):
        open_punc = tlist.token_next_match(0, T.Punctuation, '(')
        tlist.insert_after(open_punc, self.nl_with_indent(1))
        self._process_default(tlist)

        close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
        tlist.insert_before(close_punc, self.nl())


    def __process_parenthesis_for_jointables(self, tlist):
        open_punc = tlist.token_next_match(0, T.Punctuation, '(')
        self.indent += 1
        tlist.insert_after(open_punc, self.nl_with_indent(1))
        self._process_default(tlist)

        close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
        tlist.insert_before(close_punc, self.nl())

        self.indent -= 1

    def __process_parenthesis_for_with_query_cols(self, tlist):
        """
            WITHのqueryカラム名
        """
        open_punc = tlist.token_next_match(0, T.Punctuation, '(')
        self.indent += 1
        tlist.insert_after(open_punc, self.nl())
        self._process_default(tlist)

        close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
        tlist.insert_before(close_punc, self.nl())
        self.indent -= 1

    def __process_parenthesis_for_insert(self, tlist):
        open_punc = tlist.token_next_match(0, T.Punctuation, '(')
        tlist.insert_after(open_punc, self.nl())
        self._process_default(tlist)

        close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
        tlist.insert_before(close_punc, self.nl())

    def __process_parenthesis_for_complist(self, tlist):
        open_punc = tlist.token_next_match(0, T.Punctuation, '(')
        self.indent += 1
        tlist.insert_after(open_punc, self.nl())

        self._process_default(tlist)
        comps = self._get_comparisons(tlist)
        tlist.insert_before(comps[0], sql.Token(T.Whitespace, "\t"))
        self._adjust_comparisons_indent(comps)

        close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
        tlist.insert_before(close_punc, self.nl())
        self.indent -= 1

    def __process_parenthesis_for_dmlddl(self, tlist):
        open_punc = tlist.token_next_match(0, T.Punctuation, '(')

        def calc_dmlddl_indent(tlist):
            exists = False
            for tkn in self._flatten_tokens_prev(tlist):
                if tu.is_enable(tkn):
                    if tu.is_open_punctuation(tkn):
                        """
                            括弧内
                        (<--|
                            |(
                            |--->SELECT
                            |--->--->*
                            |--->FROM
                            |--->--->TBL
                            |)
                        )<--|
                        """
                        return (1, 0)
                    if tu.is_union(tkn.parent):
                        return (1, 0)
                    exists = True
                    break

            if not exists:
                """
                    前が存在しない
                    |(
                    |--->SELECT
                    |--->--->*
                    |--->FROM
                    |--->--->TBL
                    |)
                """
                return (1, 0)

            """
                通常は
                |AND AAA  =  (
                |--->--->SELECT
                |--->--->--->*
                |--->--->FROM
                |--->--->--->TBL
                |--->)
            """
            return (2, 1)


        dmlddl_indent, dmlddl_close_indent = calc_dmlddl_indent(tlist)
        self.indent += dmlddl_indent
        tlist.insert_after(open_punc, self.nl())

        self._process_default(tlist, stmts=False)

        self.__custom_process_list(tlist)

        self.indent -= (dmlddl_indent - dmlddl_close_indent)
        close_punc = tlist.token_next_match(open_punc, T.Punctuation, ')')
        tlist.insert_before(close_punc, self.nl())
        self.indent -= dmlddl_close_indent


    def _process_case(self, tlist):
        def is_prev_comma(token):
            for prev in self._flatten_tokens_prev(token):
                if not tu.is_enable(prev):
                    continue
                return tu.is_comma(prev)
            return False

        commma_next = is_prev_comma(tlist)
        cases = tu.get_cases(tlist)
        if not commma_next:
            case = tlist.tokens[0]
            tlist.insert_before(case, self.nl_with_indent(1))

        self.offset += 2
        is_first = True
        for cond, value in cases:
            if is_first:
                is_first = False
                if not value:
                    if cond:
                        tlist.insert_before(cond[0], self.nl_with_indent(-1))
                    continue

            if cond:
                tlist.insert_before(cond[0], self.nl())
                tlist.insert_after(cond[0], self.nl_with_indent(1))

            if value:
                tlist.insert_before(value[0], self.nl())
                tlist.insert_after(value[0], self.nl_with_indent(1))

        self._process_default(tlist)

        self.offset -= 2

        end = tlist.token_next_match(0, T.Keyword, 'END')
        tlist.insert_before(end, self.nl_with_indent(1))

        if not commma_next:
            tlist.insert_after(end, self.nl())

    def _process_function(self, tlist):
        func_name = tlist.token_next(-1)
        idx = tlist.token_index(func_name)

        tkn = tlist.token_next(idx, skip_ws=False)
        while tkn and tkn.is_whitespace():
            tlist.tokens.remove(tkn)
            tkn = tlist.token_next(idx, skip_ws=False)

        self._process_default(tlist)

    def _process_withingroupfunctions(self, tlist):
        for token in tlist.tokens:
            if token.is_whitespace():
                token.value = " "

        tgp = tlist.get_group()
        if tgp:
            tkn = tlist.token_next(tgp, skip_ws=False)
            while tkn and tkn.is_whitespace():
                tlist.tokens.remove(tkn)
                tkn = tlist.token_next(tgp, skip_ws=False)

        self._process_function(tlist.get_main_function())
        self.__custom_process_inorder_function(tlist.get_group())

    def _process_phrase(self, tlist, kwds=True):
        self._process_default(tlist, kwds=kwds)

        for tkn in tlist.tokens_words():
            if tkn.is_whitespace():
                tkn.value = " "

    def _process_ascdesc(self, tlist):
        self._process_default(tlist)

        for tkn in tlist.tokens_words():
            if tkn.is_whitespace():
                tkn.value = " "

    def _process_offsetfetch(self, tlist):
        self._process_default(tlist)

        for tkn in tlist.tokens_words():
            if tkn.is_whitespace():
                tkn.value = " "

        tlist.insert_before(tlist.tokens[0], self.nl())

    def _process_limitoffset(self, tlist):
        def remove_whitespace(tokens, parent): # 空白の削除
            tokens = tokens[:]
            for token in tokens:
                if token.is_whitespace():
                    parent.tokens.remove(token)

        def proc_csv(tokens, parent): # カンマ形式の処理
            tokens = tokens[:]

            for token in tokens:
                if tu.is_comma(token):
                    next_token = parent.token_next(token, skip_ws=False)
                    if next_token and next_token.is_whitespace():
                        next_token.value = " "
                    else:
                        parent.insert_after(token, sql.Token(T.Whitespace, " "))

        self._process_default(tlist)

        has_comma = False
        identifier_list = None
        for tkn in tlist.tokens_words():
            if tu.is_comma(tkn):
                has_comma = True
                break
            if tu.is_identifier_list(tkn):
                identifier_list = tkn
                break

        if has_comma :# LIMIT num, num 形式
            remove_whitespace(tlist.tokens, tlist)

            proc_csv(tlist.tokens, tlist)

            for tkn in tlist.tokens_words():
                if tu.is_keyword(tkn):
                    tlist.insert_after(tkn, sql.Token(T.Whitespace, " "))
                    tlist.insert_before(tkn, self.nl())
        elif identifier_list :# LIMIT num, num 形式
            remove_whitespace(tlist.tokens, tlist)
            remove_whitespace(identifier_list.tokens, identifier_list)

            proc_csv(identifier_list.tokens, identifier_list)

            for tkn in tlist.tokens_words():
                if tu.is_keyword(tkn):
                    tlist.insert_after(tkn, sql.Token(T.Whitespace, " "))
                    tlist.insert_before(tkn, self.nl())
        else : # LIMIT num / LIMIT num OFFSET num 形式
            for tkn in tlist.tokens_words():
                if tkn.is_whitespace():
                    tkn.value = " "
                elif tu.is_keyword(tkn):
                    tlist.insert_before(tkn, self.nl())



    def _process_mergewhen(self, tlist):
        self._process_default(tlist)

        for tkn in tlist.tokens_words():
            if tkn.is_whitespace():
                tkn.value = " "

        tlist.insert_before(tlist.tokens[0], self.nl())

    def _process_overfunctions(self, tlist):
        """
            ROW_NUMBERなどのOVERが付く系
        """
        for token in tlist.tokens:
            if token.is_whitespace():
                token.value = " "

        self._process_function(tlist.get_main_function())
        self.__custom_process_inorder_function(tlist.get_over())

    def _process_keepfunctions(self, tlist):
        """
            KEEPが付く系
        """
        for token in tlist.tokens:
            if token.is_whitespace():
                token.value = " "

        self._process_function(tlist.get_main_function())
        self.__custom_process_inorder_function(tlist.get_keep())

    def _process_forupdate(self, tlist, kwds=True):
        self.__custom_process_list(tlist)
        self._process_default(tlist, kwds=kwds)


        tlist.insert_before(tlist.get_for(), self.nl())

        if tlist.is_in_identifier():
            prev = None
            for tkn in tlist.tokens_between(tlist.get_for(), tlist.get_of()):
                if tkn.is_whitespace():
                    if prev and prev.is_whitespace():
                        tlist.tokens.remove(tkn)
                    else:
                        tkn.value = " "
                prev = tkn


            tlist.insert_after(tlist.get_of(), self.nl_with_indent(1))

            if tlist.get_wait_or_nowait():
                tlist.insert_before(tlist.get_wait_or_nowait(), self.nl())
        else:
            prev = None
            for tkn in tlist.tokens_between(tlist.get_for(),tlist.get_target_tokens()[-1]):
                if tkn.is_whitespace():
                    if prev and prev.is_whitespace():
                        tlist.tokens.remove(tkn)
                    else:
                        tkn.value = " "
                prev = tkn

        tlist.insert_after(tlist.get_target_tokens()[-1], self.nl())

    def _process_waitornowait(self, tlist, _=True):
        for tkn in tlist.tokens_words():
            if tkn.is_whitespace():
                tkn.value = " "

    def _process_union(self, tlist, kwds=True):
        self._process_phrase(tlist, kwds)

        tlist.insert_before(tlist.tokens[0], self.nl())
        tlist.insert_after(tlist.tokens[-1], self.nl())

    def _process_join(self, tlist):
        """
            JOIN系
        """
        tlist.insert_before(tlist.jointoken, self.nl())
        tlist.insert_before(tlist.identifiertoken, self.nl_with_indent(1))
        self._process_default(tlist.identifiertoken)
        if tlist.usingtoken:
            tlist.insert_before(tlist.usingtoken, self.nl())
            tokens = tlist.tokens_between(tlist.usingtoken, tlist.usingparenthesistoken)[1:-1]
            for tkn in tokens:
                if tkn.is_whitespace():
                    tkn.value = ''
            self.indent += 1
            self.__process_parenthesis_for_join_using(tlist.usingparenthesistoken)
            self.indent -= 1



    def _process_on(self, tlist):
        """
            ON句
        """
        token = tlist.token_next_match(0, T.Keyword, 'ON')
        try:
            tlist.insert_before(token, self.nl())
            tlist.insert_after(token, self.nl_with_indent(1))
        except ValueError:  # issue121, errors in statement
            pass

        self._process_default(tlist)
        self._adjust_comparisons_indent(self._get_comparisons(tlist))


    def _process_mergeupdateinsertclause(self, tlist):
        """
            MERGEの内のUPDATE・INSERT句
        """
        self.indent += 1
        self.__custom_process_list(tlist)
        self._process_default(tlist)
        self.indent -= 1


        tkn = tu.token_next_enable(tlist)
        if tkn and tu.is_insert_dml(tkn):
            self.__custom_process_insert_values_lr(tlist)

    def _process_connectby(self, tlist):
        """
            CONNECT BY句
        """
        token = tlist.token_matching(0, (tu.is_phrase ,))
        try:
            tlist.insert_before(token, self.nl())
            tlist.insert_after(token, self.nl_with_indent(1))
        except ValueError:  # issue121, errors in statement
            pass

        self._process_default(tlist)
        self._adjust_comparisons_indent(self._get_comparisons(tlist))

    def _process_startwith(self, tlist):
        """
            START WITH句
        """
        token = tlist.token_matching(0, (tu.is_phrase ,))
        try:
            tlist.insert_before(token, self.nl())
            tlist.insert_after(token, self.nl_with_indent(1))
        except ValueError:  # issue121, errors in statement
            pass

        self._process_default(tlist)
        self._adjust_comparisons_indent(self._get_comparisons(tlist))

    def _process_with(self, tlist):
        """
            WITH句
        """
        with_token = tlist.token_with()
        tlist.insert_before(with_token, self.nl())
        tlist.insert_after(with_token, self.nl_with_indent(1))
        self._process_default(tlist)

    def _process_specialfunctionparameter(self, tlist):
        """
            特殊パラメータ
        """
        for tkn in tlist.tokens_words():
            if tkn.is_whitespace():
                tkn.value = " "
            elif tkn.is_group():
                self._process(tkn)


    def nl_with_indent(self, offset):
        count = ((self.indent * self.width) + self.offset + offset)
        if count < 0:
            count = 0
        space = "\t" * count
        sws = '\n' + space
        return sql.Token(T.Whitespace, sws)

    def cr(self):
        return sql.Token(T.Whitespace, '\n')

    def indent_space(self, offset=0):
        space = ("\t" * ((self.indent * self.width) + self.offset + offset))
        return sql.Token(T.Whitespace, space)

    def one_indent_space(self):
        return sql.Token(T.Whitespace, "\t")

    def _adjust_identifiers_indent(self, identifiers):
        """
            Identifierの内部インデントの調整
        """

        if not identifiers:
            return

        def is_update_set_identifiers(token):
            if not self.__within_update_set_section(token):
                return False

            while token.parent:
                parent = token.parent
                if tu.is_parenthesis(parent):
                    return False
                if (not parent.parent) or (not self.__within_update_set_section(parent)):
                    return True
                token = parent
            return True

        fst = identifiers[0]
        ids = []
        if is_update_set_identifiers(fst):
            # update set句
            for token in identifiers:
                if not token.is_group():
                    continue
                ids.append(_UpdIdentifierObject(token, self.indent + self.offset, self.local_config))
        else:
            for token in identifiers:
                if not token.is_group():
                    continue
                ids.append(_IdentifierObject(token, self.indent + self.offset, self.local_config))


        max_width_left = 0
        max_width_right = 0
        has_center_token = False
        for identifier in ids:
            max_width_left = max(max_width_left, identifier.width_left)
            max_width_right = max(max_width_right, identifier.width_right)
            has_center_token = has_center_token or identifier.center_token

        left_offset = 0 if has_center_token else -1

        for identifier in ids:
            if identifier.right_tokens:
                left = identifier.left_lines[-1]
                left_space = "\t" * int(calc_tab_padding_count(left, max_width_left)  + left_offset)
                if len(identifier.left_lines) > 1:
                    left_space += "\t"
                identifier.token.insert_after(identifier.left_tokens[-1], sql.Token(T.Whitespace, left_space))

                if identifier.line_comment:
                    right = identifier.right_lines[-1]
                    right_space = "\t" * int(calc_tab_padding_count(right, max_width_right))
                    if len(identifier.right_lines) > 1:
                        right_space += "\t\t"  + ("\t" * int(calc_tab_padding_count("", max_width_left) + left_offset))
                    identifier.token.insert_after(identifier.right_tokens[-1], sql.Token(T.Whitespace, right_space))
            elif identifier.line_comment:
                left = identifier.left_lines[-1]

                left_space = "\t" * int(calc_tab_padding_count(left, max_width_left) + left_offset) \
                        + "\t" \
                        + "\t" * int(calc_tab_padding_count("", max_width_right))
                if len(identifier.left_lines) > 1:
                    left_space += "\t"
                identifier.token.insert_after(identifier.left_tokens[-1], sql.Token(T.Whitespace, left_space))

    def _adjust_comparisons_indent(self, comparisons):
        """
            Comparisonの内部インデントの調整
        """

        ids = []
        for token in comparisons:
            if not token.is_group():
                continue
            if tu.is_comparison(token):
                ids.append(_ComparisonObject(token, self.indent + self.offset, self.local_config))

        max_width_left = 0
        max_width_operator = 0
        max_width_right = 0
        for comparison in ids:
            max_width_left = max(max_width_left, comparison.width_left)
            max_width_operator = max(max_width_operator, comparison.width_operator)
            max_width_right = max(max_width_right, comparison.width_right)

        for comparison in ids:
            if comparison.right_tokens:
                left = comparison.left_lines[-1]
                left_space = "\t" * int(calc_tab_padding_count(left, max_width_left))
                if len(comparison.left_lines) > 1:
                    left_space += "\t"
                comparison.token.insert_after(comparison.left_tokens[-1], sql.Token(T.Whitespace, left_space))

                op_space = "\t" * int(calc_tab_padding_count(comparison.operator_string, max_width_operator))
                comparison.token.insert_after(comparison.operator_tokens[-1], sql.Token(T.Whitespace, op_space))

                if comparison.line_comment:
                    right = comparison.right_lines[-1]
                    right_space = "\t" * int(calc_tab_padding_count(right, max_width_right))
                    if len(comparison.right_lines) > 1:
                        right_space += "\t\t"  + ("\t" * int(calc_tab_padding_count("", max_width_left)))
                    comparison.token.insert_after(comparison.right_tokens[-1], sql.Token(T.Whitespace, right_space))


    def _flatten_tokens_prev(self, token):
        return tu.flatten_tokens_prev(self._curr_stmt, token)

    def _flatten_tokens_next(self, token):
        return tu.flatten_tokens_next(self._curr_stmt, token)

    def _get_comparisons(self, token):
        return list(x for x in token.tokens if tu.is_comparison(x) or tu.is_parenthesis(x) or tu.is_exists_function(x))


    def _is_include_format_target_identifire_list_parenthesis(self, parenthesis):
        """
            括弧がフォーマットが必要なidentifirelistを有するかどうか
        """
        def find_identifire_list(token):
            if tu.is_identifier_list(token):
                return token
            if isinstance(token, sql.TokenList):
                for tkn in token.tokens:
                    til = find_identifire_list(tkn)
                    if til:
                        return til
            return None

        def is_include_line_comment(identifier):
            for tkn in identifier.tokens:
                if tu.is_line_comment(tkn):
                    return True
            return False

        til = find_identifire_list(parenthesis)
        if not til:
            return False

        identifiers = list(til.get_identifiers())
        # ラインコメントが無ければ対象外
        for identifier in identifiers:
            if is_include_line_comment(identifier):
                return True

        return False

    def _is_format_target_identifire_list(self, identifirelist):
        """
            フォーマットが必要なidentifirelistかどうか
        """

        identifiers = list(identifirelist.get_identifiers())
        if not identifiers:
            return False

        func_token = tu.within_function(self._curr_stmt, identifirelist)
        if not func_token:
            # 関数内でなければ処理する
            return True

        if tu.is_exists_function(func_token) or tu.is_over_function(func_token):
            # existsとover内は処理する
            return True

        parenthesis = tu.within_parenthesis(self._curr_stmt, identifirelist)

        if tu.is_dmlddl_parenthesis(parenthesis):
            return True
        if tu.is_comparisons_parenthesis(parenthesis):
            return True
        if self._is_include_format_target_identifire_list_parenthesis(parenthesis):
            return True

        return False

    def __indent_shift(self, tlist, shift=1):
        for token in tu.flatten(tlist):
            if is_inc_cr(token):
                token.value += "\t" * shift

def hit_last(token, func, skip_ws=True):
    if func(token):
        return token
    if token.is_group():
        for tkn in token.tokens[::-1]:
            if hit_last(tkn, func):
                return tkn
            if skip_ws and tkn.is_whitespace():
                continue
            else:
                break
    return None

def hit_first(token, func, skip_ws=True):
    if func(token):
        return token
    if token.is_group():
        for tkn in token.tokens[:]:
            if hit_first(tkn, func):
                return tkn
            if skip_ws and tkn.is_whitespace():
                continue
            else:
                break
    return None

def calc_tab_padding_count(text, size):
    width = get_text_char_width(text)
    if size < width :
        #サイズオーバー
        return 1

    count = 0
    mod = width % 4
    if mod > 0 :
        width += 4 - mod
        count += 1
    count += math.ceil((size - width) / 4)
    return count

def calc_tab_pad_size(size):
    mod = size % 4
    if mod == 0:
        return size + 4
    else:
        return size + 4 - mod

def get_need_tab_char_width(text) :
    return calc_tab_pad_size(get_text_char_width(text))

def get_text_char_width(text) :
    if sys.version_info[0] < 3 and isinstance(text, str):
        text = text.decode('utf-8')
    width = 0
    for cval in text:
        if cval =="\t":
            width = calc_tab_pad_size(width)
        elif is_zen(cval):
            width += 2
        else:
            width += 1

    return width

def is_zen(cval):
    regexp = re.compile(r'(?:\xEF\xBD[\xA1-\xBF]|\xEF\xBE[\x80-\x9F])|[\x20-\x7E]')
    result = regexp.search(cval)
    return not result

def is_inc_cr(token):
    return token.is_whitespace() and ("\n" in token.value or "\r" in token.value)
