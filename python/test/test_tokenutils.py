# coding:utf-8
'''
Created on 2016/07/27

@author: ota
'''

import unittest
from uroborosqlfmt import tokenutils as tu


class Test(unittest.TestCase):

    def test1(self):
        self.assertEqual(tu.equals_ignore_case("ABC","a"), False)
        self.assertEqual(tu.equals_ignore_case("ABC","A"), False)
        self.assertEqual(tu.equals_ignore_case("ABC","B"), False)
        self.assertEqual(tu.equals_ignore_case("ABC","abc"), True)
        self.assertEqual(tu.equals_ignore_case("ABC","aBc"), True)
        self.assertEqual(tu.equals_ignore_case("ABC","ABC"), True)

    def test2(self):
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","b"), False)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","c"), False)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","B"), False)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","abcdefgh"), False)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","a"), True)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","abc"), True)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","aBc"), True)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","ABC"), True)
        self.assertEqual(tu.startswith_ignore_case("ABCdefg","abcdefg"), True)

    def test3(self):
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","b"), False)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","c"), False)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","B"), False)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","abcdefgh"), False)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","ABC"), False)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","g"), True)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","efg"), True)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","eFg"), True)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","EFG"), True)
        self.assertEqual(tu.endswith_ignore_case("ABCdefg","abcdefg"), True)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
