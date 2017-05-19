# coding:utf-8
'''
uroboroSQL formatter.
@author: ota
'''


__version__ = '0.0.1'

import sys
import re
from threading import Thread, Lock
import sqlparse
from sqlparse.lexer import Lexer
from sqlparse import tokens as T, utils
from uroborosqlfmt import filters, config

LOCK = Lock()

def format_sql(sql, local_config = config.LocalConfig()):

    LOCK.acquire()
    try:
        if not config.glb.escape_sequence_u005c:
            # Oracle等の場合リテラルの取り方が違うので置き換える
            for i, data in enumerate(Lexer.tokens["root"]):
                single = getattr(T.String, "Single")
                if data[0] == r"'(''|\\\\|\\'|[^'])*'" :
                    if data[1] == single:
                        Lexer.tokens["root"][i] = (r"'(''|[^'])*'", single)

                        # 初期化
                        if hasattr(Lexer, "_tokens"):
                            delattr(Lexer, "_tokens")
                        if hasattr(Lexer, "token_variants"):
                            delattr(Lexer, "token_variants")
                        break
            utils.SPLIT_REGEX = re.compile(r"""
            (
             (?:                     # Start of non-capturing group
              (?:\r\n|\r|\n)      |  # Match any single newline, or
              [^\r\n'"]+          |  # Match any character series without quotes or
                                     # newlines, or
              "(?:[^"]|\\.)*"   |  # Match double-quoted strings, or
              '(?:[^']|\\.)*'      # Match single quoted strings
             )
            )
            """, re.VERBOSE)
        else:
            # 元に戻す
            for i, data in enumerate(Lexer.tokens["root"]):
                single = getattr(T.String, "Single")
                if data[0] == r"'(''|[^'])*'" :
                    if data[1] == single:
                        Lexer.tokens["root"][i] = (r"'(''|\\\\|\\'|[^'])*'" , single)

                        # 初期化
                        if hasattr(Lexer, "_tokens"):
                            delattr(Lexer, "_tokens")
                        if hasattr(Lexer, "token_variants"):
                            delattr(Lexer, "token_variants")
                        break
            utils.SPLIT_REGEX = re.compile(r"""
            (
             (?:                     # Start of non-capturing group
              (?:\r\n|\r|\n)      |  # Match any single newline, or
              [^\r\n'"]+          |  # Match any character series without quotes or
                                     # newlines, or
              "(?:[^"\\]|\\.)*"   |  # Match double-quoted strings, or
              '(?:[^'\\]|\\.)*'      # Match single quoted strings
             )
            )
            """, re.VERBOSE)
    finally:
        LOCK.release()

    stack = sqlparse.engine.FilterStack()
    stack.enable_grouping()

    if local_config.uppercase and local_config.input_reserved_words:
        stack.preprocess.append(sqlparse.filters.KeywordCaseFilter('lower'))
        stack.preprocess.append(sqlparse.filters.IdentifierCaseFilter('lower'))
        stack.preprocess.append(filters.ReservedWordCaseFilter(local_config))
    elif local_config.uppercase:
        stack.preprocess.append(sqlparse.filters.KeywordCaseFilter())
        stack.preprocess.append(sqlparse.filters.IdentifierCaseFilter())

    stack.stmtprocess.append(filters.GroupFilter())
    stack.stmtprocess.append(filters.LineDescriptionLineCommentFilter(local_config))
    stack.stmtprocess.append(filters.MoveCommaFilter(local_config))
    stack.stmtprocess.append(filters.StripWhitespaceAndToTabFilter())
    stack.stmtprocess.append(filters.AdjustGroupFilter(local_config))

    stack.stmtprocess.append(filters.OperatorFilter())

    stack.stmtprocess.append(filters.CustomReindentFilter(local_config))
    stack.postprocess.append(sqlparse.filters.SerializerUnicode())

    if sys.version_info[0] < 3 and isinstance(sql, unicode):
        sql = sql.encode("utf-8")
        formatted = "\n".join(stack.run(sql))
        return formatted.decode("utf-8")
    else:
        return "\n".join(stack.run(sql))
