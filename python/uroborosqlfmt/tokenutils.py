# coding:utf-8
'''
@author: ota
'''
import re
from sqlparse import sql, tokens as T
from enum import Enum


class EngineComment(Enum):
    """
        SQLエンジン関連コメントType
    """
    none = 0 # SQLエンジン関連コメントではない
    syntax = 1 # ロジック
    param = 2 # パラメータ
    sql_identifier = 3 # SQL_IDENTIFIER

def get_comment_type(token, comment_syntax):
    """
        SQLエンジン関連コメントTypeを返す
    """
    if is_block_comment(token):
        return comment_syntax.get_block_comment_type(token)
    elif is_line_comment(token):
        return comment_syntax.get_line_comment_type(token)

def is_param_comment(token, next_token, comment_syntax):
    """
        SQLエンジンのパラメータコメント判定
    """
    return get_comment_type(token, comment_syntax) == EngineComment.param \
        and (is_literal(next_token) or is_wildcard(next_token) or is_parenthesis(next_token))

def is_hint_block_comment(token):
    """
        Oracleヒントコメント判定
    """
    if is_block_comment(token):
        tokens = token.tokens
        if len(tokens) >= 3 :
            comment = tokens[1].value
            if comment.startswith("+"):
                return True
    return False

def is_block_comment(token):
    """
        ブロックコメント判定
    """
    if is_comment(token):
        comment = token.token_next_by_type(0, T.Comment)
        return comment.value in ["/*", "*/"]

    return False

def is_line_comment(token):
    """
        ラインコメント判定
    """
    if is_comment(token):
        comment = token.token_next_by_type(0, T.Comment)
        return comment.value not in ["/*", "*/"]
    return False

def is_plain_line_comment(token, comment_syntax):
    """
        ラインコメント（SQLエンジン構文ではない）判定
    """
    return is_line_comment(token) and get_comment_type(token, comment_syntax) == EngineComment.none

def is_line_description_line_comment(token, comment_syntax):
    """
        ラインコメント（行説明になりうる）判定
    """
    return is_plain_line_comment(token, comment_syntax) and token.is_line_description

def is_comment(token):
    """
        コメント判定
    """
    return isinstance(token, sql.Comment)

def is_dot(token):
    """
        ドット判定
    """
    return is_punctuation(token) and token.value == "."

def is_comma(token):
    """
        カンマ判定
    """
    return is_punctuation(token) and token.value == ","

def is_literal(token):
    """
        リテラル判定（文字列・数値）
    """
    return token.ttype in T.Literal

def is_string_literal(token):
    """
        リテラル判定（文字列）
    """
    return token.ttype in T.Literal.String

def is_number_literal(token):
    """
        リテラル判定（数値）
    """
    return token.ttype in T.Literal.Number

def is_null_keyword(token):
    """
        「NULL」文字列判定
    """
    return token.match(T.Keyword, "NULL")

def is_comparison(token):
    """
        比較演算判定
    """
    return isinstance(token, sql.Comparison)

def is_identifier_list(token):
    """
        IdentifierList判定
    """
    return isinstance(token, sql.IdentifierList)

def is_identifier(token):
    """
        Identifier判定
    """
    return isinstance(token, sql.Identifier)

def is_function(token):
    """
        関数判定
    """
    return isinstance(token, sql.Function)

def is_value_candidate(token):
    """
        値になりうる
    """
    return is_string_candidate(token) or is_number_candidate(token)


def is_string_candidate(token):
    """
        文字列になりうる
    """
    if is_string_literal(token):
        return True
    if is_function(token):
        return True
    if is_null_keyword(token):
        return True
    if is_calculation(token):
        return True
    if is_parenthesis(token):
        tokens = [t for t in tokens_parenthesis_inner(token) if is_enable(t)]
        if len(tokens) == 1:
            return is_string_candidate(tokens[0])
        elif tokens:
            return is_select_dml(tokens[0])
    if is_identifier(token):
        tokens = [t for t in token.tokens if is_enable(t)]
        for tkn in tokens:
            if (not tkn.ttype in T.Name) and (not is_dot(tkn)):
                return False
        return True

    return False

def is_number_candidate(token):
    """
        数値になりうる
    """
    if is_number_literal(token):
        return True
    if is_function(token):
        return True
    if is_null_keyword(token):
        return True
    if is_calculation(token):
        return True
    if is_parenthesis(token):
        tokens = [t for t in tokens_parenthesis_inner(token) if is_enable(t)]
        if len(tokens) == 1:
            return is_number_candidate(tokens[0])
        elif tokens:
            return is_select_dml(tokens[0])
    if is_identifier(token):
        tokens = [t for t in token.tokens if is_enable(t)]
        for tkn in tokens:
            if (not tkn.ttype in T.Name) and (not is_dot(tkn)):
                return False
        return True

    return False

def is_exists_function(token):
    """
        EXISTS関数判定
    """
    if not is_function(token):
        return False
    ftoken = token_next_enable(token)
    return equals_ignore_case(ftoken.value, "EXISTS")

def is_over_function(token):
    """
        OVER関数判定
    """
    if not is_function(token):
        return False
    ftoken = token_next_enable(token)
    return equals_ignore_case(ftoken.value, "OVER")

def is_parenthesis(token):
    """
        括弧判定
    """
    return isinstance(token, sql.Parenthesis)

def is_dmlddl_parenthesis(token):
    """
        DMLかDDLの括弧判定
    """
    if not is_parenthesis(token):
        return False


    open_punc = token.token_next_match(0, T.Punctuation, '(')
    first = token_next_enable(token, open_punc)
    if first and first.ttype in (T.Keyword.DML, T.Keyword.DDL):
        return True

    if is_with(first):
        return True

    if is_parenthesis(first):
        return is_dmlddl_parenthesis(first)

    return False

def is_enum_parenthesis(token):
    """
        括弧の中身が値の列挙かどうかの判定
    """
    if not is_parenthesis(token):
        return False

    def is_enums(tokens):
        for token in tokens:
            if token.is_whitespace() \
                or is_comment(token) \
                or is_comma(token) \
                or is_literal(token) \
                or is_null_keyword(token) \
                or is_identifier(token):
                pass
            elif is_identifier_list(token):
                if not is_enums(token.tokens):
                    return False
            else:
                return False
        return True

    return is_enums(tokens_parenthesis_inner(token))

def is_comparisons_parenthesis(token):
    """
        括弧の中身が比較演算かどうかの判定
    """
    if not is_parenthesis(token):
        return False

    exists_logical_operator = False
    exists_comparison_operator = False
    exists_parenthesis = False
    exists_exists_function = False
    prev_enable = None
    for tkn in tokens_parenthesis_inner(token):
        if is_comparison(tkn):
            return True
        if is_logical_operator_keyword(tkn):
            exists_logical_operator = True
        if is_comparison_operator(tkn):
            exists_comparison_operator = True
        if prev_enable and get_comparison_operator_words(prev_enable, tkn):
            exists_comparison_operator = True
        if is_parenthesis(tkn):
            exists_parenthesis = True
        if is_exists_function(tkn):
            exists_exists_function = True
        if exists_logical_operator and exists_comparison_operator:
            return True
        if exists_logical_operator and exists_parenthesis:
            return True
        if exists_logical_operator and exists_exists_function:
            return True
        if is_enable(tkn):
            prev_enable = tkn

    return False


def is_punctuation(token):
    """
        Punctuation判定
    """
    return token.ttype in T.Punctuation

def is_semicolon_punctuation(token):
    """
        セミコロン判定
    """
    return is_punctuation(token) and token.value == ";"

def is_open_punctuation(token):
    """
        開き括弧判定
    """
    return is_punctuation(token) and token.value == "("

def is_close_punctuation(token):
    """
        閉じ括弧判定
    """
    return is_punctuation(token) and token.value == ")"

def is_keyword(token):
    """
        keyword判定
    """
    return token.is_keyword

def is_as_keyword(token):
    """
        「AS」判定
    """
    return token.match(T.Keyword, "AS")

def is_distinct_keyword(token):
    """
        「DISTINCT」判定
    """
    return token.match(T.Keyword, "DISTINCT")

def is_from_keyword(token):
    """
        「FROM」判定
    """
    return token.match(T.Keyword, "FROM")

def is_by_keyword(token):
    """
        「BY」判定
    """
    return token.match(T.Keyword, "BY")

def is_select_dml(token):
    """
        SELECT句判定
    """
    return token.match(T.DML, "SELECT")

def is_update_dml(token):
    """
        UPDATE句判定
    """
    return token.match(T.DML, "UPDATE")

def is_insert_dml(token):
    """
        INSERT句判定
    """
    return token.match(T.DML, "INSERT")

def is_delete_dml(token):
    """
        DELETE句判定
    """
    return token.match(T.DML, "DELETE")

def is_with(token):
    """
        WITH句判定
    """
    from uroborosqlfmt.sql import With
    return isinstance(token, With)

def is_into_keyword(token):
    """
        INTO判定
    """
    return token.match(T.Keyword, "INTO")

def is_values_keyword(token):
    """
        VALUES判定
    """
    return token.match(T.Keyword, "VALUES")

def is_set_keyword(token):
    """
        SET判定
    """
    return token.match(T.Keyword, "SET")

def is_dml(token):
    """
        DML判定
    """
    return token.ttype in T.DML

def is_wildcard(token):
    """
        ワイルドカード「*」判定
    """
    return token.ttype in T.Wildcard

def is_where(token):
    """
        WHERE句判定
    """
    return isinstance(token, sql.Where)

def is_when(token):
    """
        WHEN句判定
    """
    from uroborosqlfmt.sql import When
    return isinstance(token, When)

def is_having(token):
    """
        HAVING句判定
    """
    from uroborosqlfmt.sql import Having
    return isinstance(token, Having)

def is_on(token):
    """
        ON句判定
    """
    from uroborosqlfmt.sql import On
    return isinstance(token, On)

def is_connectby(token):
    """
        CONNECT BY句判定
    """
    from uroborosqlfmt.sql import ConnectBy
    return isinstance(token, ConnectBy)

def is_startwith(token):
    """
        START WITH句判定
    """
    from uroborosqlfmt.sql import StartWith
    return isinstance(token, StartWith)

def is_case(token):
    """
        CASE句判定
    """
    return isinstance(token, sql.Case)

def is_forupdate(token):
    """
        FOR UPDATE句判定
    """
    from uroborosqlfmt.sql import ForUpdate
    return isinstance(token, ForUpdate)

def is_waitornowait(token):
    """
        WAIT / NOWAIT句判定
    """
    from uroborosqlfmt.sql import WaitOrNowait
    return isinstance(token, WaitOrNowait)

def is_union(token):
    """
        UNION句判定
    """
    from uroborosqlfmt.sql import Union
    return isinstance(token, Union)

def is_join(token):
    """
        JOIN句判定
    """
    from uroborosqlfmt.sql import Join
    return isinstance(token, Join)

def is_mergewhen(token):
    """
        WHEN句判定
    """
    from uroborosqlfmt.sql import MergeWhen
    return isinstance(token, MergeWhen)

def is_mergeupdateinsertclause(token):
    """
         MERGEの内のDML判定
    """
    from uroborosqlfmt.sql import MergeUpdateInsertClause
    return isinstance(token, MergeUpdateInsertClause)


def is_between_keyword(token):
    """
        「BETWEEN」判定
    """
    return token.match(T.Keyword, "BETWEEN")

def is_and_keyword(token):
    """
        AND演算子判定
    """
    return token.match(T.Keyword, "AND")

def is_using_keyword(token):
    """
        USING判定
    """
    return token.match(T.Keyword, "USING")

def is_logical_operator_keyword(token):
    """
        AND・OR演算子判定
    """
    return token.match(T.Keyword, ("AND", "OR"))

def is_name_or_keyword(token):
    """
        name or keyword判定
    """
    return is_keyword(token) or token.ttype in T.Name

def is_operator(token):
    """
        演算子判定
    """
    return token.ttype in T.Operator

def is_comparison_operator(token):
    """
        比較演算子判定
    """
    return token.ttype in T.Operator.Comparison

def is_concat_operator(token):
    """
        文字列連結演算子判定
    """
    return is_operator(token) and token.value == "||"

def is_phrase(token):
    """
        Phrase判定
    """
    from uroborosqlfmt.sql import Phrase
    return isinstance(token, Phrase)

def is_calculation(token):
    """
        演算判定
    """
    from uroborosqlfmt.sql import Calculation
    return isinstance(token, Calculation)

def is_calc_operator(token):
    """
        演算子判定
    """
    if is_concat_operator(token):
        return True
    if is_operator(token) and not is_comparison_operator(token):
        return True

    return False


def is_enable(token):
    """
        有効Token判定（コメント・空白以外）
    """
    if token.is_whitespace():
        return False
    if is_comment(token):
        return False
    if token.parent and is_comment(token.parent):
        return False
    return True


def find_comparison_operator_words(tokens):
    """
        比較演算子の検索
    """
    prev = None
    for token in tokens[:]:
        if not is_enable(token):
            continue
        if not prev:
            prev = token
            continue

        comps = get_comparison_operator_words(prev, token)
        if comps:
            return comps
        prev = token

    if prev:
        return get_comparison_operator_words(prev, None)
    else:
        return []

def get_comparison_operator_words(token, next_token):
    """
        比較演算子の取得
    """
    if next_token and is_keyword(next_token):
        if is_keyword(token):
            if equals_ignore_case(token.value, "NOT"):
                if equals_ignore_case(next_token.value, ["IN", "BETWEEN", "LIKE"]):
                    return [token, next_token]
            elif equals_ignore_case(token.value, "IS"):
                if equals_ignore_case(next_token.value, ["NOT"]):
                    return [token, next_token]
                else:
                    return [token]
        elif is_comparison_operator(token):
            if equals_ignore_case(next_token.value, ["ANY", "SOME", "ALL"]):
                return [token, next_token]
            else:
                return [token]
    else:
        if is_keyword(token):
            if equals_ignore_case(token.value, ["IN", "BETWEEN", "LIKE", "IS"]):
                return [token]
        elif is_comparison_operator(token):
            return [token]
    return []

def tokens_parenthesis_inner(parenthesis):
    """
        括弧内Tokenリストの取得
    """
    open_punc = parenthesis.token_next_match(0, T.Punctuation, '(')
    close_punc = parenthesis.token_next_match(open_punc, T.Punctuation, ')')
    return parenthesis.tokens_between(open_punc, close_punc)[1:-1]

def token_function_inner_parenthesis(func):
    ftoken = token_next_enable(func)
    return token_next_enable(func, ftoken)


def token_next_enable(token, idx = -1):
    """
        次の有効Tokenの取得
    """
    if not isinstance(idx, int):
        idx = token.token_index(idx)
    return token.token_matching(idx + 1, [is_enable])

def token_prev_enable(token, idx = -1):
    """
        前の有効Tokenの取得
    """
    if not isinstance(idx, int):
        idx = token.token_index(idx)

    if idx < 0:
        idx = len(token.tokens)
    prv = token.token_prev(idx)

    while is_comment(prv):
        prv = token.token_prev(prv)
    return prv

def flatten_tokens_prev(top_token, token):
    """
        前Tokenのgenerator
    """
    tgt = next(flatten(token))
    iterator = flatten(top_token)
    tokens = []
    for tkn in iterator:
        if tkn == tgt:
            break
        tokens.append(tkn)
    for tkn in tokens[::-1]:
        yield tkn

def flatten_tokens_next(top_token, token):
    """
        後Tokenのgenerator
    """
    tgt = list(flatten(token))[-1]
    iterator = flatten(top_token)
    for tkn in iterator:
        if tkn == tgt:
            break
    for tkn in iterator:
        yield tkn

def token_parents(token):
    """
        親Tokenのgenerator
    """
    while token:
        yield token
        token = token.parent

def token_top_matching(token, sub, func):
    """
        親を走査してヒットするTokenがあるか判定
    """
    def in_parents(tkn):
        for parent in token_parents(sub):
            if tkn == parent:
                return True
        return False

    parents = token_parents(token)
    tkn = None
    for parent in parents:
        if func(parent):
            if in_parents(parent):
                return None
            tkn = parent
            break

    for parent in parents:
        if in_parents(parent):
            return tkn
        if not func(parent):
            return tkn
        tkn = parent
    return tkn


def within_with_section(stmt, token):
    """
        WITH句内判定
    """
    for tkn in tokens_tree_up(stmt, token):
        if equals_ignore_case(tkn.value, "WITH"):
            return tkn
        if is_dml(tkn):
            return None
    return None

def within_select_statement(stmt, token):
    """
        SELECT句内判定
    """
    for tkn in tokens_tree_up(stmt, token):
        if is_dml(tkn):
            if equals_ignore_case(tkn.value, "SELECT"):
                return tkn
            return None
    return None

def within_update_statement(stmt, token):
    """
        UPDATE句内判定
    """
    for tkn in tokens_tree_up(stmt, token):
        if is_dml(tkn):
            if equals_ignore_case(tkn.value, "UPDATE"):
                return tkn
            return None
    return None

def within_insert_statement(stmt, token):
    """
        INSERT句内判定
    """
    for tkn in tokens_tree_up(stmt, token):
        if is_dml(tkn):
            if equals_ignore_case(tkn.value, "INSERT"):
                return tkn
            return None
    return None

def within_merge_statement(stmt, token):
    """
        MERGE句内判定
    """
    for tkn in tokens_tree_up(stmt, token):
        if is_dml(tkn):
            if equals_ignore_case(tkn.value, "MERGE"):
                return tkn
            return None
    return None

def within_insert_values_section(stmt, token):
    """
        INSERTのVALUES句内判定
    """
    itr = tokens_tree_up(stmt, token)
    for tkn in itr:
        if is_parenthesis(tkn):
            break

    for tkn in itr:
        if is_enable(tkn):
            if is_values_keyword(tkn):
                return tkn
            return None
    return None

def within_insert_into_columns_section(stmt, token):
    """
        INSERTのカラム内判定
    """
    itr = tokens_tree_up(stmt, token)
    for tkn in itr:
        if is_parenthesis(tkn):
            break

    for tkn in itr:
        if is_enable(tkn):
            if is_identifier(tkn):
                break
            elif is_insert_dml(tkn):
                return tkn
            else:
                return None

    for tkn in itr:
        if is_enable(tkn):
            if is_into_keyword(tkn):
                return tkn
            return None
    return None


def within_update_set_section(stmt, token):
    """
        UPDATEのSET句内判定
    """
    if not within_update_statement(stmt, token):
        return None
    if within_where_section(stmt, token):
        return None

    itr = tokens_tree_up(stmt, token)
    for tkn in itr:
        if is_set_keyword(tkn):
            return tkn

    return None

def within_where_section(stmt, token):
    """
        WHERE句内判定
    """
    for tkn in tokens_tree_up(stmt, token):
        if equals_ignore_case(tkn.value, "WHERE"):
            return tkn
        if is_dml(tkn):
            return None
    return None

def within_function(stmt, token):
    """
        関数内判定
    """
    for tkn in get_roots(stmt, token)[:]:
        if is_function(tkn):
            return tkn
    return None

def within_parenthesis(stmt, token):
    """
        括弧内判定
    """
    for tkn in get_roots(stmt, token)[:]:
        if is_parenthesis(tkn):
            return tkn
    return None

def tokens_tree_up(stmt, token):
    """
        ツリー上での前へのgenerator
    """
    roots = get_roots(stmt, token)
    cld = roots.pop(0)
    while roots:
        parent = roots.pop(0)
        prevs = []
        for tkn in parent.tokens:
            prevs.append(tkn)
            if tkn == cld:
                cld = parent
                break
        for tkn in prevs[::-1]:
            yield tkn

def get_roots(parent, token):
    """
        ルートTokenリスト
    """
    for tkn in parent.tokens:
        if tkn == token:
            return [token, parent]
        if isinstance(tkn, sql.TokenList):
            ret = get_roots(tkn, token)
            if ret:
                ret.append(parent)
                return ret
    return []

def get_parent(top_parent, token):
    """
        ルートを指定した親Token取得
    """
    for tkn in top_parent.tokens:
        tkn.parent = top_parent
        if tkn == token:
            return top_parent
        if isinstance(tkn, sql.TokenList):
            ret = get_parent(tkn, token)
            if ret:
                return ret
    return None

def flatten(token):
    """
        フラット化したgenerator
        ※処理中にparentを再設定する。sql.TokenList#flattenとはここが違う
    """
    if isinstance(token, sql.TokenList):
        for tkn in token.tokens:
            tkn.parent = token
            if isinstance(tkn, sql.TokenList):
                for item in flatten(tkn):
                    yield item
            else:
                yield tkn
    else:
        yield token


CONDITION = 1
VALUE = 2

def get_cases(case):
    """Returns a list of 2-tuples (condition, value).

    If an ELSE exists condition is None.
    """


    ret = []
    mode = CONDITION

    for token in case.tokens:
        # Set mode from the current statement
        if token.match(T.Keyword, 'CASE'):
            continue

        elif is_when(token):
            ret.append(([], []))
            mode = CONDITION

        elif token.match(T.Keyword, 'THEN'):
            mode = VALUE

        elif token.match(T.Keyword, 'ELSE'):
            ret.append((None, []))
            mode = VALUE

        elif token.match(T.Keyword, 'END'):
            mode = None

        # First condition without preceding WHEN
        if mode and not ret:
            ret.append(([], []))

        # Append token depending of the current mode
        if mode == CONDITION:
            ret[-1][0].append(token)

        elif mode == VALUE:
            ret[-1][1].append(token)

    # Return cases list
    return ret

def equals_ignore_case(txt1, txt2):
    """
        大文字小文字を無視した文字列比較
    """
    if isinstance(txt2, str):
        values = {re.compile(txt2 + "$", re.IGNORECASE)}
    else:
        values = set(re.compile(v + "$", re.IGNORECASE) for v in txt2)

    for pattern in values:
        if pattern.match(txt1):
            return True
    return False

def startswith_ignore_case(target, txt):
    """
        大文字小文字を無視したstartswith
    """
    if isinstance(txt, str):
        values = {re.compile(txt, re.IGNORECASE)}
    else:
        values = set(re.compile(v, re.IGNORECASE) for v in txt)

    for pattern in values:
        if pattern.match(target):
            return True
    return False

def endswith_ignore_case(target, txt):
    """
        大文字小文字を無視したendswith
    """
    if isinstance(txt, str):
        values = {re.compile(txt + "$", re.IGNORECASE)}
    else:
        values = set(re.compile(v + "$", re.IGNORECASE) for v in txt)

    for pattern in values:
        if pattern.search(target):
            return True
    return False
