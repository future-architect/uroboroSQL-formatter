# coding:utf-8
'''
@author: ota
'''
from sqlparse import sql, tokens as T
from uroborosqlfmt import tokenutils as tu

class Having(sql.TokenList):

    __slots__ = ('value', 'ttype', 'tokens')

class When(sql.TokenList):

    __slots__ = ('value', 'ttype', 'tokens')

class On(sql.TokenList):

    __slots__ = ('value', 'ttype', 'tokens')

class _BaseWords(sql.TokenList):

    def __init__(self, tokens=None):
        super(_BaseWords, self).__init__(tokens=tokens)
        self.__target_tokens = None

    def _setupinit(self, target_tokens):
        self.__target_tokens = target_tokens

    def _token_word(self, hit_index):
        return self.__target_tokens[hit_index]

    def tokens_words(self):
        start = self._token_word(0)
        end = tu.token_prev_enable(self)
        return self.tokens_between(start, end)

    def get_target_tokens(self):
        return self.__target_tokens[:]

class WithinGroupFunctions(_BaseWords):
    """
        LISTAGG ( expr [, delimiter] ) WITHIN GROUP ( order_by )
        等のWITHIN GROUPのつく関数
    """

    __slots__ = ('value', 'ttype', 'tokens', '_main_function', '_within', '_group')

    def __init__(self, tokens=None):
        super(WithinGroupFunctions, self).__init__(tokens=tokens)
        self._main_function = None
        self._within = None
        self._group = None

    def get_main_function(self):
        return self._main_function

    def get_within(self):
        return self._within

    def get_group(self):
        return self._group

class Phrase(_BaseWords):
    """
        ORDER BY、GROUP BYなど
    """

    __slots__ = ('value', 'ttype', 'tokens')


    def match_phrase(self, values):
        tokens = self.get_target_tokens()
        if len(tokens) != len(values):
            return False

        for i, token in enumerate(tokens):
            if not tu.equals_ignore_case(token.value, values[i]):
                return False

        return True

class AscDesc(_BaseWords):
    """
        ASC DESCなど
    """

    __slots__ = ('value', 'ttype', 'tokens')

class OffsetFetch(_BaseWords):
    """
        OFFSET句、FETCH句
    """

    __slots__ = ('value', 'ttype', 'tokens')

class LimitOffset(_BaseWords):
    """
        LIMIT・OFFSET句
    """

    __slots__ = ('value', 'ttype', 'tokens')

class OverFunctions(_BaseWords):
    """
        ROW_NUMBER句など
    """

    __slots__ = ('value', 'ttype', 'tokens')

    def get_main_function(self):
        return self._token_word(0)

    def get_over(self):
        return self._token_word(1)

class KeepFunctions(_BaseWords):
    """
        KEEPのつく関数
    """

    __slots__ = ('value', 'ttype', 'tokens')


    def get_main_function(self):
        return self._token_word(0)

    def get_keep(self):
        return self._token_word(1)

class ForUpdate(_BaseWords):
    """
        FOR UPDATE
    """

    __slots__ = ('value', 'ttype', 'tokens')

    def get_for(self):
        return self._token_word(0)

    def get_update(self):
        return self._token_word(1)

    def get_of(self):
        for tkn in self.tokens:
            if tu.equals_ignore_case(tkn.value, "OF"):
                return tkn
        return None

    def get_wait_or_nowait(self):
        tokens = self.get_target_tokens()
        if len(tokens) < 3:
            return False

        for tkn in tokens[::-1]:
            if tu.is_waitornowait(tkn):
                return tkn
        return None

    def is_in_identifier(self):
        return self.get_of()

class WaitOrNowait(_BaseWords):
    """
        WAIT / NOWAIT
    """

    __slots__ = ('value', 'ttype', 'tokens')

    def get_wait_or_nowait(self):
        return self._token_word(0)

class Union(_BaseWords):
    """
        UNION系
    """

    __slots__ = ('value', 'ttype', 'tokens')


class Join(_BaseWords):
    """
        JOIN系
    """

    __slots__ = ('value', 'ttype', 'tokens', 'jointoken', 'identifiertoken', 'usingtoken', 'usingparenthesistoken')

class MergeWhen(_BaseWords):
    """
        MERGEのWHEN句
    """

    __slots__ = ('value', 'ttype', 'tokens')

class MergeUpdateInsertClause(_BaseWords):
    """
        MERGEの内のUPDATE・INSERT句
    """

    __slots__ = ('value', 'ttype', 'tokens')

class ConnectBy(_BaseWords):
    """
        ORACLEのCONNECT BY句
    """

    __slots__ = ('value', 'ttype', 'tokens')

class StartWith(_BaseWords):
    """
        ORACLEのSTART WITH句
    """

    __slots__ = ('value', 'ttype', 'tokens')

class With(_BaseWords):
    """
        ORACLEのWITH句
    """

    __slots__ = ('value', 'ttype', 'tokens')


    def token_with(self):
        return self.token_next_match(0, T.Keyword, 'WITH')

class SpecialFunctionParameter(_BaseWords):
    """
        ANSIのTRIM
        ORACLEのTRIM
        PostgreSQLのSUBSTRING
        等のパラメータ
    """

    __slots__ = ('value', 'ttype', 'tokens')

class Calculation(_BaseWords):
    """
        計算値
    """

    __slots__ = ('value', 'ttype', 'tokens')
