# coding:utf-8
'''
@author: ota
'''
from uroborosqlfmt.commentsyntax import UroboroSqlCommentSyntax


class _GlobalConfig(object):
    def __init__(self):
        self.escape_sequence_u005c = False  # バックスラッシュによるエスケープシーケンス

    def set_escape_sequence_u005c(self, escape_sequence):
        self.escape_sequence_u005c = escape_sequence
        return self


class LocalConfig(object):

    __slots__ = ('comment_syntax', 'uppercase', 'input_reserved_words')

    def __init__(self):
        self.comment_syntax = UroboroSqlCommentSyntax()
        self.uppercase = True
        self.input_reserved_words = None

    def set_commentsyntax(self, comment_syntax):
        self.comment_syntax = comment_syntax
        return self

    def set_uppercase(self, uppercase):
        self.uppercase = uppercase
        return self

    def set_input_reserved_words(self, input_reserved_words):
        self.input_reserved_words = input_reserved_words
        return self


# グローバル設定
glb = _GlobalConfig()  # pylint: disable=invalid-name
