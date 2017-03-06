# coding:utf-8
'''
Created on 2016/07/05

@author: ota
'''
import unittest
import uroborosqlfmt


class Test(unittest.TestCase):

    def test1(self):
        self.assertEqual(format_sql("""
SELECT
/* _SQL_ID_ */
    EMP.EMP_NO      AS  EMP_NO
,   EMP.FIRST_NAME  AS  FIRST_NAME
,   EMP.LAST_NAME   AS  LAST_NAME
,   EMP.BIRTH_DATE  AS  BIRTH_DATE
,   EMP.GENDER      AS  GENDER
FROM
    EMPLOYEE    EMP /*BEGIN*/
WHERE
/*IF SF.isNotEmpty(emp_no)*/
AND EMP.EMP_NO  =   /*emp_no*/1
/*END*/
/*IF female != null and female*/
AND EMP.GENDER  =   /*#CLS_GENDER_FEMALE*/'M'
/*END*/
/*END*/
        """), "SELECT /* _SQL_ID_ */\n\tEMP.EMP_NO\t\tAS\tEMP_NO\n,\tEMP.FIRST_NAME\tAS\tFIRST_NAME\n,\tEMP.LAST_NAME\tAS\tLAST_NAME\n,\tEMP.BIRTH_DATE\tAS\tBIRTH_DATE\n,\tEMP.GENDER\t\tAS\tGENDER\nFROM\n\tEMPLOYEE\tEMP\n/*BEGIN*/\nWHERE\n/*IF SF.isNotEmpty(emp_no)*/\nAND\tEMP.EMP_NO\t=\t/*emp_no*/1\n/*END*/\n/*IF female != null and female*/\nAND\tEMP.GENDER\t=\t/*#CLS_GENDER_FEMALE*/'M'\n/*END*/\n/*END*/\n")

    def test2(self):
        self.assertEqual(format_sql("""
select * from tbl where 1 = 1 and(2 = 2)
        """),'SELECT\n\t*\nFROM\n\tTBL\nWHERE\n\t1\t=\t1\nAND\t(\n\t\t2\t=\t2\n\t)')

def format_sql(text):
    formated = uroborosqlfmt.format_sql(text)
#     print(formated)
#     print(repr(formated))

    return formated


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
