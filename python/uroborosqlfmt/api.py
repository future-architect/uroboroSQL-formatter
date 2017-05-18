# coding:utf-8
'''
uroboroSQL formatter API.
@author: ota
'''

import os
import traceback
import codecs
import sys
import argparse
import uroborosqlfmt
from uroborosqlfmt import config
from uroborosqlfmt import commentsyntax
from uroborosqlfmt.exceptions import SqlFormatterException
from uroborosqlfmt.config import LocalConfig

# pylint: disable=bare-except


def format_dir(indir, outdir, local_config):
    """
        [indir]フォルダ内のSQLファイルをフォーマットして指定フォルダ[outdir]に出力する
    """
    if indir.endswith("/") or indir.endswith("\\"):
        indir = indir[:-1]
    if outdir.endswith("/") or outdir.endswith("\\"):
        outdir = outdir[:-1]

    for file_name, full_path in find_all_sql_files(indir):
        try:
            sql = __read_file(full_path)
        except:
            print(full_path)
            print(traceback.format_exc())
            continue
        error = False
        try:
            out_sql = uroborosqlfmt.format_sql(sql, local_config)
        except SqlFormatterException as ex:
            exs = __decode(str(ex))
            trace = __decode(traceback.format_exc())
            out_sql = sql + "\n/*" + exs + "\n" + trace + "\n*/"
            error = True
        except:
            trace = __decode(traceback.format_exc())
            out_sql = sql + "\n/*" + trace + "\n*/"
            error = True

        if not error:
            out_path = os.path.join(outdir, file_name)
        else:
            out_path = os.path.join(outdir, "formaterror_" + file_name)
        out_dir = os.path.dirname(out_path)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        __write_file(out_path, out_sql)


def format_file(infile, outdir, local_config):
    """
        SQLファイル(infile)をフォーマットして指定フォルダ[outdir]に出力する
    """
    try:
        sql = __read_file(infile)
    except:
        print(infile)
        print(traceback.format_exc())

    error = False

    try:
        out_sql = uroborosqlfmt.format_sql(sql, local_config)
    except SqlFormatterException as ex:
        exs = __decode(str(ex))
        trace = __decode(traceback.format_exc())
        out_sql = sql + "\n/*" + exs + "\n" + trace + "\n*/"
        error = True
    except:
        trace = __decode(traceback.format_exc())
        out_sql = sql + "\n/*" + trace + "\n*/"
        error = True

    if not error:
        file_name = os.path.basename(infile)
        out_path = os.path.join(outdir, file_name)
    else:
        out_path = os.path.join(outdir, "formaterror_" + file_name)
    out_dir = os.path.dirname(out_path)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    __write_file(out_path, out_sql)


def find_all_sql_files(directory):
    for root, _, files in os.walk(directory):
        for file_name in files:
            if os.path.splitext(file_name)[1].lower() == ".sql":
                path = os.path.join(root, file_name)
                yield path[len(directory) + 1:], path


def __read_file(path):
    target_file = codecs.open(path, "r", "utf-8")
    ret = target_file.read()
    target_file.close()
    return ret


def __write_file(path, value):
    target_file = codecs.open(path, "w", "utf-8")
    target_file.write(value)
    target_file.close()


def __decode(text):
    text = str(text)
    if sys.version_info[0] < 3:
        return text.decode("utf-8")
    else:
        return text

def _parse_args(test_args=None):
    parser = argparse.ArgumentParser(description='uroboroSQL formatter API', prog='usqlfmt')

    parser.add_argument('-v', '--version', action='version', version='%(prog)s 0.1.0')
    parser.add_argument('input_path', \
        action='store', \
        type=str, \
        help='input directory path or input file path', \
        )
    parser.add_argument('output_path', \
        action='store', \
        type=str, \
        help='output path for formatted file(s).', \
        )
    parser.add_argument('-m', '--mode', \
        action='store', \
        default='file', \
        type=str, \
        choices=['file', 'directory'], \
        help='format target. default "file"', \
        )

    parser.add_argument('-N', '--nochange_case', \
        action='store_true', \
        help='UPPERCASE off.', \
        )
    parser.add_argument('-B', '--escapesequence_u005c', \
        action='store_true', \
        help='use backslash escapesequence.', \
        )
    parser.add_argument('-c', '--comment_syntax', \
        action='store', \
        default='uroborosql', \
        type=str, \
        choices=['uroborosql', 'doma2', 'uroboro', 'doma'], \
        help='SQL comment out syntax type.', \
        )
    parser.add_argument('-r', '--reserved_words_file_path', \
        action='store', \
        default=None, \
        type=str, \
        help='input reserved words file path.', \
        )

    return parser.parse_args(test_args)


def __execute():

    """
    Check the arguments.
    If the number of arguments does not match the specified number,
    quit the application with usage massages.
    """
    args = _parse_args()

    mode = args.mode
    nochange_case = args.nochange_case
    escapesequence_u005c = args.escapesequence_u005c
    comment_syntax = args.comment_syntax
    input_path = args.input_path
    output_path = args.output_path
    reserved_words_file_path = args.reserved_words_file_path
    local_config = LocalConfig()

    set_uppercase(local_config, not nochange_case)
    set_escapesequence_u005c(escapesequence_u005c)
    set_comment_syntax(local_config, comment_syntax)
    set_reserved_words(local_config, reserved_words_file_path)

    """
    The application requires either "file" or "directory"
    as a command line argument. If the argument does not match them,
    quit the application with usage massages.
    """
    if mode == "file":
        format_file(input_path, output_path, local_config)
    elif mode == "directory":
        format_dir(input_path, output_path, local_config)
    else:
        sys.exit()

    print("\n===== Finish the application =====")
    print("Output directory path : %s" % output_path)
    print("=====           End          =====")


def set_uppercase(local_config, uppercase):
    local_config.set_uppercase(uppercase)


def set_escapesequence_u005c(escapesequence_u005c):
    config.glb.escape_sequence_u005c = escapesequence_u005c


def set_comment_syntax(local_config, comment_syntax):
    if comment_syntax == "uroborosql" or comment_syntax == "uroboro":
        local_config.set_commentsyntax(commentsyntax.UroboroSqlCommentSyntax())
    elif comment_syntax == "doma2" or comment_syntax == "doma":
        local_config.set_commentsyntax(commentsyntax.Doma2CommentSyntax())
    else:
        sys.exit()


def set_reserved_words(local_config, reserved_words_file):
    if reserved_words_file is not None:
        try:
            f = open(reserved_words_file, 'r')
            lines = f.readlines()
            f.close()
        except IOError:
            print("File I/O error: %s" % reserved_words_file)
            print("Please check the file path.")
            sys.exit("Application quitting...")
        except:
            print ("Unexpected error:", sys.exc_info()[0])
            sys.exit("Application quitting...")
        else:
            reserved_words = []

            for line in lines:
                reserved_words.append(line.rstrip('\n').lower())  # Eliminate newline code.

            local_config.set_input_reserved_words(reserved_words)


if __name__ == "__main__":
    __execute()
