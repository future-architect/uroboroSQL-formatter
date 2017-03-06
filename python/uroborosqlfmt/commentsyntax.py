# coding:utf-8
'''
@author: ota
'''
import re
from sqlparse import tokens as T
from uroborosqlfmt.tokenutils import EngineComment
from uroborosqlfmt import tokenutils as tu


# pylint: disable=unused-argument
class CommentSyntax(object):
    def __init__(self):
        pass
    def get_block_comment_type(self, token):
        return EngineComment.none

    def get_line_comment_type(self, token):
        return EngineComment.none
# pylint: enable=unused-argument

class UroboroSqlCommentSyntax(CommentSyntax):

    def get_block_comment_type(self, token):
        tokens = token.tokens
        if len(tokens) >= 3 :
            comment = tokens[1].value
            if comment.strip() == "_SQL_ID_" or comment.strip() == "_SQL_IDENTIFIER_":
                return EngineComment.sql_identifier # _SQL_IDENTIFIER_
            if tu.startswith_ignore_case(comment, ("IF", "ELIF", "ELSE", "END", "BEGIN")):
                return EngineComment.syntax
            if comment.strip() == comment and (not comment.startswith("*")) and (not comment.startswith("+")):
                return EngineComment.param # param
        return EngineComment.none

    def get_line_comment_type(self, token):
        cmm = token.token_next_by_type(0, T.Comment)
        comment = cmm.value[2:]
        if tu.startswith_ignore_case(comment.strip(), "ELSE"):
            return EngineComment.syntax
        return EngineComment.none


class Doma2CommentSyntax(CommentSyntax):

    def get_block_comment_type(self, token):
        tokens = token.tokens
        if len(tokens) >= 3 :
            comment = tokens[1].value
            first_char = comment[0]
            if first_char == " " or \
                re.compile("[a-z]", re.IGNORECASE).match(first_char) or \
                first_char == "^" or \
                first_char == "$" or \
                first_char == "#" or \
                first_char == "@" or \
                first_char == '"' or \
                first_char == "'":
                return EngineComment.param
            if first_char == "%":
                if tu.startswith_ignore_case(comment[1:], "expand"):
                    return EngineComment.param
                return EngineComment.syntax
        return EngineComment.none

# /* ～*/ ...--3文字目が空白であるため式コメントです。
# /*a～*/ ...--3文字目がJavaの識別子の先頭で使用可能な文字であるため式コメントです。
# /*$～*/ ...--3文字目がJavaの識別子の先頭で使用可能な文字であるため式コメントです。
# /*%～*/ ...--3文字目が条件コメントや繰り返しコメントの始まりを表す「%」であるため式コメントです。
# /*#～*/ ...--3文字目が埋め込み変数コメントを表す「#」であるため式コメントです。
# /*@～*/ ...--3文字目が組み込み関数もしくはクラス名を表す「@」であるため式コメントです。
# /*"～*/ ...--3文字目が文字列リテラルの引用符を表す「"」であるため式コメントです。
# /*'～*/ ...--3文字目が文字リテラルの引用符を表す「'」であるため式コメントです。
