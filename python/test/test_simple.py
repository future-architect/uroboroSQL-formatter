# coding:utf-8
'''
Created on 2016/07/05

@author: ota
'''
import unittest
import uroborosqlfmt
from uroborosqlfmt.config import LocalConfig


class Test(unittest.TestCase):

    def test1(self):
        self.assertEqual(format_sql("""
select * from dual
        """), 'SELECT\n\t*\nFROM\n\tDUAL')

    def test2(self):
        self.assertEqual(format_sql("""
select COL_a, col_b from table_01 where col_c is null and col_d = 1 -- コメント

        """),'SELECT\n\tCOL_A\n,\tCOL_B\nFROM\n\tTABLE_01\nWHERE\n\tCOL_C\tIS\tNULL\nAND\tCOL_D\t=\t1\t\t-- コメント\n')

    def test3(self):
        self.assertEqual(format_sql(u"""
select t.COL_a as a -- コメント1
, t.col_b as b -- コメント2
, /*CLS*/'0' as hoge_kbn -- コメント3
from table_01 t -- コメント4
where t.col_c is null -- コメント5
and t.col_d = 1 -- コメント6
and t.col_e between 1 and 2 -- コメント7

        """),u"SELECT\n\tT.COL_A\t\tAS\tA\t\t\t-- コメント1\n,\tT.COL_B\t\tAS\tB\t\t\t-- コメント2\n,\t/*CLS*/'0'\tAS\tHOGE_KBN\t-- コメント3\nFROM\n\tTABLE_01\tT\t-- コメント4\nWHERE\n\tT.COL_C\tIS\t\tNULL\t\t-- コメント5\nAND\tT.COL_D\t=\t\t1\t\t\t-- コメント6\nAND\tT.COL_E\tBETWEEN\t1\tAND\t2\t-- コメント7\n") # pylint: disable=line-too-long

    def test4(self):
        self.assertEqual(format_sql(u"""
select t.COL_a as a -- コメント1
, t.col_b as b -- コメント2
, /*CLS*/'0' as hoge_kbn -- コメント3
from table_01 t -- コメント4
where t.col_c is null -- コメント5
and t.col_d = 1 -- コメント6
and t.col_e between 1 and 2 -- コメント7
order by t.col_a asc, t.col_b desc nulls first -- コメント
, t.col_c -- コメント

        """),u"SELECT\n\tT.COL_A\t\tAS\tA\t\t\t-- コメント1\n,\tT.COL_B\t\tAS\tB\t\t\t-- コメント2\n,\t/*CLS*/'0'\tAS\tHOGE_KBN\t-- コメント3\nFROM\n\tTABLE_01\tT\t-- コメント4\nWHERE\n\tT.COL_C\tIS\t\tNULL\t\t-- コメント5\nAND\tT.COL_D\t=\t\t1\t\t\t-- コメント6\nAND\tT.COL_E\tBETWEEN\t1\tAND\t2\t-- コメント7\nORDER BY\n\tT.COL_A\tASC\n,\tT.COL_B\tDESC NULLS FIRST\t-- コメント\n,\tT.COL_C\t\t\t\t\t\t-- コメント\n") # pylint: disable=line-too-long

    def test5(self):
        self.assertEqual(format_sql(u"""
SELECT NO, NAME FROM (
     SELECT NO, NAME,
            ROW_NUMBER() OVER (ORDER BY NO) RNUM
     FROM ROWNUM_TEST
 ) WHERE RNUM BETWEEN 5 AND 10
        """), u"SELECT\n\tNO\n,\tNAME\nFROM\n\t(\n\t\tSELECT\n\t\t\tNO\n\t\t,\tNAME\n\t\t,\tROW_NUMBER() OVER(\n\t\t\t\tORDER BY\n\t\t\t\t\tNO\n\t\t\t)\t\tRNUM\n\t\tFROM\n\t\t\tROWNUM_TEST\n\t)\nWHERE\n\tRNUM\tBETWEEN\t5\tAND\t10") # pylint: disable=line-too-long

def format_sql(text):
    formated = uroborosqlfmt.format_sql(text, LocalConfig())

    return formated


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
