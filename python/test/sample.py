# coding:utf-8
'''
Created on 2016/07/27

@author: ota
'''

import uroborosqlfmt
from uroborosqlfmt.config import LocalConfig

def sample():
    sql = u"""
select column1 as column1, --column1
column2 as column2 --column1
,long_column_3 as long_long_column_3 --column3
from foo_table --table
where column1 = 'sample' --column1
and long_column_3 is not null
"""

    formatted = uroborosqlfmt.format_sql(sql, LocalConfig())

    print(formatted)

if __name__ == "__main__":
    sample()
