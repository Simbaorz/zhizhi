# -*- coding: utf-8 -*-
import os
import sys
import logging
from time import strftime
# 输出日志路径
# if os.name == 'nt':
#     PATH = 'C:/logs'
# else:
#     PATH = '/logs'

# NAME = 'pymysql'
# 设置日志格式#和时间格式
FMT = '%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s: %(message)s'
DATEFMT = '%Y-%m-%d %H:%M:%S'

class MyLog(object):
    _instance = None
    def __new__(cls, *args, **kw):
        if cls._instance is None:
            MyLog._instance = object.__new__(cls)
        return MyLog._instance

    def __init__(self,config = None):
        # if config:
        #     path = config.get('logpath')
        #     name = config.get('logname')
        # else:
        #     path = PATH
        #     name = NAME

        # if os.path.exists(path) == False:
        #     os.mkdir(path)
           
        self.logger = logging.getLogger(__name__)
        self.logger.propagate = False
        self.formatter = logging.Formatter(fmt=FMT, datefmt=DATEFMT)
        # self.log_filename = '{0}{1}.log'.format(PATH, strftime("%Y-%m-%d"))
        #self.log_filename = '{0}/{1}.log'.format(path, name)

        #self.logger.addHandler(self.get_file_handler(self.log_filename))
        self.logger.addHandler(self.get_console_handler())
        # 设置日志的默认级别
        self.logger.setLevel(logging.DEBUG)

    @classmethod
    def get_instance(cls):
        return cls._instance

    # 输出到文件handler的函数定义
    def get_file_handler(self, filename):
        filehandler = logging.FileHandler(filename, encoding="utf-8")
        filehandler.setFormatter(self.formatter)
        return filehandler

    # 输出到控制台handler的函数定义
    def get_console_handler(self):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(self.formatter)
        return console_handler

