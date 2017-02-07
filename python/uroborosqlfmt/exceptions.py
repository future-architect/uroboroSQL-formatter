# coding:utf-8
'''
Created on 2016/07/09

@author: ota
'''
import sys
import traceback

class SqlFormatterException(Exception):
    '''
        SqlFormatter用のExceptionクラス
    '''

    def __init__(self, tlist, ex, trace):
        super(SqlFormatterException, self).__init__(ex.message if hasattr(ex, "message") else "")
        self.tlist = self.__decode(tlist)
        self.e = ex
        self.trace = self.__decode(trace)
        self.message = ex.message

    def __decode(self, text):
        text = str(text)
        if sys.version_info[0] < 3:
            return text.decode("utf-8")
        else:
            return text

    def __encode(self, text):
        if sys.version_info[0] < 3 and isinstance(text, unicode):
            return text.encode("utf-8")
        else:
            return text

    def __str__(self, *args):
        return self.message \
                + "\ntoken:"  + self.__encode(self.tlist) \
                + "\ntrace:"  + self.__encode(self.trace) \
                + "\noriginal:"  + str(self.e)

    @staticmethod
    def wrap_try_except(fnc, token, *args):
        try:
            if args:
                return fnc(*args)
            else:
                return fnc(token)
        except Exception as ex:
            if not isinstance(ex, SqlFormatterException):
                raise SqlFormatterException(token, ex, traceback.format_exc())
            raise

    @staticmethod
    def to_wrap_try_except(fnc, token_arg_index):
        def call(*args):
            try:
                return fnc(*args)
            except Exception as ex:
                if not isinstance(ex, SqlFormatterException):
                    raise SqlFormatterException(args[token_arg_index], ex, traceback.format_exc())
                raise
        return call
