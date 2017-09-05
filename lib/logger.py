# Copyright (C) IBM Corp. 2016.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Python wrapper for avocado
# Author: Satheesh Rajendran<sathnaga@linux.vnet.ibm.com>


import os
import logging


class logger_init:

    def __init__(self, level=logging.DEBUG, name='avocado-wrapper', filepath=None):
        # Create the logger
        self.logger = logging.getLogger(name)
        if not getattr(self.logger, 'handler_set', None):
            self.logger.setLevel(level)
            self.level = level
            self.name = name
            self.filepath = filepath
            self.filename = None
            file_formatter = logging.Formatter(
                '%(asctime)s %(levelname)-8s: [%(filename)s:%(lineno)d] %(message)s',
                '%Y-%m-%d %H:%M:%S')
            console_formatter = logging.Formatter(
                '%(asctime)s %(levelname)-8s: %(message)s',
                '%H:%M:%S')

            if not self.filepath:
                self.filename = "/tmp/%s.log" % self.name
            else:
                if not os.path.isdir(self.filepath):
                    os.system('mkdir -p %s' % self.filepath)
                self.filename = "%s/%s.log" % (self.filepath, self.name)

            self.file_hdlr = logging.FileHandler(self.filename)
            self.file_hdlr.setFormatter(file_formatter)
            self.file_hdlr.setLevel(logging.DEBUG)
            self.logger.addHandler(self.file_hdlr)

            self.console_handler = logging.StreamHandler()
            self.console_handler.setFormatter(console_formatter)
            self.console_handler.setLevel(logging.INFO)
            self.logger.addHandler(self.console_handler)
            self.logger.handler_set = True

    def getlogger(self):
        return self.logger
