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
        self.assertEqual(format_sql(u"""
select
/*+ hint  */
col1 as col1 -- AAA
,
col2 as col2 -- BBB
,col_long_3 as col3 -- CCC
from table1
where col1 = 'value' -- col1 condition
and col2 = 'val'-- col2 condition
and col_long_3 in (1,2,3)
        """), u"SELECT\n/*+\n\thint\n*/\n\tCOL1\t\tAS\tCOL1\t-- AAA\n,\tCOL2\t\tAS\tCOL2\t-- BBB\n,\tCOL_LONG_3\tAS\tCOL3\t-- CCC\nFROM\n\tTABLE1\nWHERE\n\tCOL1\t\t=\t'value'\t\t-- col1 condition\nAND\tCOL2\t\t=\t'val'\t\t-- col2 condition\nAND\tCOL_LONG_3\tIN\t(1, 2, 3)") # pylint: disable=line-too-long

    def test2(self):
        self.assertEqual(format_sql(u"""
select
/*+ hint  */
sum(col1) as col1 -- AAA
,
AVG(col2) as col2 -- BBB
,col_long_3 as col3 -- CCC
from table1
where
 col_long_3 in (1,2,3)
group by col_long_3
        """), u'SELECT\n/*+\n\thint\n*/\n\tSUM(COL1)\tAS\tCOL1\t-- AAA\n,\tAVG(COL2)\tAS\tCOL2\t-- BBB\n,\tCOL_LONG_3\tAS\tCOL3\t-- CCC\nFROM\n\tTABLE1\nWHERE\n\tCOL_LONG_3\tIN\t(1, 2, 3)\nGROUP BY\n\tCOL_LONG_3') # pylint: disable=line-too-long

    def test3(self):
        self.assertEqual(format_sql(u"""
select
     color_code                   -- カラーコード
     ,CASE color_code
       WHEN 'FFF' THEN 'WHITE'     -- FFF なら白
       WHEN '000' THEN 'BACK'      -- 000 なら黒
       ELSE             color_code -- それ以外ならコード値を戻す
     END color_name
  from
     color_sample;
        """), u"SELECT\n\tCOLOR_CODE\t\t\t-- カラーコード\n,\tCASE\n\t\tCOLOR_CODE\n\t\tWHEN\n\t\t\t'FFF'\n\t\tTHEN\n\t\t\t'WHITE'\t-- FFF なら白\n\t\tWHEN\n\t\t\t'000'\n\t\tTHEN\n\t\t\t'BACK'\t-- 000 なら黒\n\t\tELSE\n\t\t\tCOLOR_CODE\t-- それ以外ならコード値を戻す\n\tEND\tCOLOR_NAME\nFROM\n\tCOLOR_SAMPLE\n;\n") # pylint: disable=line-too-long

    def test4(self):
        self.assertEqual(format_sql(u"""
    select * from employees
where
job_id in ('JOB001','JOB003')
and job_id in (select job_id from job_mst where job_kbn = '1')
        """), u"SELECT\n\t*\nFROM\n\tEMPLOYEES\nWHERE\n\tJOB_ID\tIN\t('JOB001', 'JOB003')\nAND\tJOB_ID\tIN\t(\n\t\tSELECT\n\t\t\tJOB_ID\n\t\tFROM\n\t\t\tJOB_MST\n\t\tWHERE\n\t\t\tJOB_KBN\t=\t'1'\n\t)") # pylint: disable=line-too-long

    def test5(self):
        self.assertEqual(format_sql(u"""
SELECT * FROM tab2 ORDER BY c2 OFFSET 2 ROWS FETCH FIRST 3 ROWS ONLY
        """), u'SELECT\n\t*\nFROM\n\tTAB2\nORDER BY\n\tC2\nOFFSET 2 ROWS\nFETCH FIRST 3 ROWS ONLY')
        self.assertEqual(format_sql(u"""
SELECT * FROM tab2 ORDER BY c2 FETCH FIRST 3 ROWS WITH TIES
        """), u'SELECT\n\t*\nFROM\n\tTAB2\nORDER BY\n\tC2\nFETCH FIRST 3 ROWS WITH TIES')
        self.assertEqual(format_sql(u"""
SELECT * FROM tab2 ORDER BY c02 FETCH FIRST 50 PERCENT ROWS ONLY
        """), u'SELECT\n\t*\nFROM\n\tTAB2\nORDER BY\n\tC02\nFETCH FIRST 50 PERCENT ROWS ONLY')

    def test6(self):
        self.assertEqual(format_sql(u"""
    select * from staff T1 where exists
      ( select * from staff T2 where T1.staff_id = T2.manager_id)
        """), u'SELECT\n\t*\nFROM\n\tSTAFF\tT1\nWHERE\n\tEXISTS(\n\t\tSELECT\n\t\t\t*\n\t\tFROM\n\t\t\tSTAFF\tT2\n\t\tWHERE\n\t\t\tT1.STAFF_ID\t=\tT2.MANAGER_ID\n\t)') # pylint: disable=line-too-long
        self.assertEqual(format_sql(u"""
 select * from staff T1 where not exists
      ( select * from staff T2 where T1.staff_id = T2.manager_id)
        """), u'SELECT\n\t*\nFROM\n\tSTAFF\tT1\nWHERE\n\tNOT\tEXISTS(\n\t\tSELECT\n\t\t\t*\n\t\tFROM\n\t\t\tSTAFF\tT2\n\t\tWHERE\n\t\t\tT1.STAFF_ID\t=\tT2.MANAGER_ID\n\t)') # pylint: disable=line-too-long

    # Returning句のテスト
    def test7(self):
        self.assertEqual(format_sql(u"""
    UPDATE products SET price = price * 1.10
  WHERE price <= 99.99 RETURNING name, price AS new_price;
        """), u'UPDATE\n\tPRODUCTS\nSET\tPRICE\t=\tPRICE\t*\t1.10\nWHERE\n\tPRICE\t<=\t99.99\nRETURNING\n\tNAME\n,\tPRICE\tAS\tNEW_PRICE\n;\n') # pylint: disable=line-too-long
        self.assertEqual(format_sql(u"""
   INSERT INTO users (firstname, lastname) VALUES ('Joe', 'Cool') RETURNING id, firstname, lastname;
        """), u"""INSERT\nINTO\n\tUSERS\n(\n\tFIRSTNAME\n,\tLASTNAME\n) VALUES (\n\t'Joe'\n,\t'Cool'\n)\nRETURNING\n\tID\n,\tFIRSTNAME\n,\tLASTNAME\n;\n""") # pylint: disable=line-too-long
        self.assertEqual(format_sql(u"""
   DELETE FROM products WHERE obsoletion_date = 'today' RETURNING *;
        """), u"""DELETE\nFROM\n\tPRODUCTS\nWHERE\n\tOBSOLETION_DATE\t=\t'today'\nRETURNING\t*\n;\n""") # pylint: disable=line-too-long


def format_sql(text):
    formated = uroborosqlfmt.format_sql(text, LocalConfig())

    return formated


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
