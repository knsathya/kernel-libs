import smtplib
import threading
import asyncore
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jsonparser import JSONParser
import logging
import re
import pkg_resources
import smtpd

class CustomSMTPServer(smtpd.SMTPServer):
    def process_message(self, peer, mailfrom, rcpttos, data):
        return

class Email(object):
    """
    Wrapper class for sending email.
    """
    def __init__(self, cfg=None, logger=None):
        """
        Email init()
        :param cfg: Json config file, if given smtp/form/to paramaters will be parsed from Json.
        :param logger: Logger object.
        """
        self.logger = logger or logging.getLogger(__name__)

        # SMTP server related param defaults.
        self.smtp_server = None
        self.smtp_thread = None
        self.server_obj = None
        self.client_obj = None
        self.smtp_port = 0
        self.supported_auths = ['TLS']
        self.auth = None
        self.username = None
        self.password = None

        # Config file related defaults.
        self.cfg_src = cfg
        self.cfg = None
        self.cfgobj = None
        self.schema = pkg_resources.resource_filename('klibs', 'schemas/email-schema.json')

        # Set from/to/cc/bcc defaults
        self._from = None
        self._to = None
        self._cc = None
        self._bcc = None

        # Update params if cfg file is given.
        if cfg is not None:
            set_def = lambda x, y: self.cfg[x] if self.cfg[x] != "" else y
            self.cfgobj = JSONParser(self.schema, cfg, extend_defaults=True, os_env=True, logger=logger)
            self.cfg = self.cfgobj.get_cfg()

            self.set_header(self.cfg["from"], self.cfg["to"], self.cfg["cc"], self.cfg["bcc"])
            self.set_smtp(self.cfg["smtp-server"], self.cfg["smtp-port"],
                          self.cfg["smtp-authentication"], self.cfg["smtp-username"],
                          self.cfg["smtp-password"])
    def _smtp_setup(self):

        str_check = lambda x: x is not None and isinstance(x, basestring) and len(x) > 0

        if not str_check(self.smtp_server):
            self.logger.error("Invalid SMTP server %s", self.smtp_server)
            return False

        if not self.smtp_port >= 0 or not isinstance(self.smtp_port, (int, long)):
            self.logger.error("Invalid SMTP port %s", str(self.smtp_port))
            return False

        if self.smtp_server == "localhost":
            self.server_obj = CustomSMTPServer((self.smtp_server, self.smtp_port), None)
            self.smtp_thread = threading.Thread(target=asyncore.loop, name="Asyncore Loop", kwargs = {'timeout':1})
            self.smtp_thread.start()

        self.client_obj = smtplib.SMTP(host=self.smtp_server, port=self.smtp_port)

        if str_check(self.auth) and self.auth in self.supported_auths and self.smtp_server != "localhost":
            if self.auth == 'TLS':
                self.client_obj.starttls()

        if str_check(self.username) and str_check(self.password) and self.smtp_server != "localhost":
            self.client_obj.login(self.username, self.password)

        self.logger.debug("SMTP Server Open():%s port:%d\n", self.smtp_server, self.smtp_port)

    def _smtp_close(self):
        self.client_obj.quit()
        if self.server_obj is not None:
            self.server_obj.close()
        if self.smtp_thread is not None:
            self.smtp_thread.join()
        self.logger.debug("SMTP Server Close()\n")

    def _valid_email(self, data):

        def valid(email):
            if re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
                self.logger.info("Valid email %s", email)
                return True
            else:
                self.logger.info("Invalid email %s", email)

        if isinstance(data, list):
            for item in data:
                if not valid(item):
                    return False
            return True
        elif isinstance(data, basestring):
            if valid(data):
                return True

        return False

    def set_smtp(self, smtp_server=None, smtp_port=None, auth=None, username=None, password=None):

        def check_val(val, type):
            return (val is not None and isinstance(val, type))

        if check_val(smtp_server, basestring):
            self.smtp_server = smtp_server

        if check_val(smtp_port, (int, long)):
            self.smtp_port = smtp_port

        if check_val(auth, basestring) and auth in self.supported_auths:
            self.auth = auth

        if check_val(username, basestring):
            self.username = username

        if check_val(password, basestring):
            self.password = password

    def set_header(self, _from, _to=[], _cc=[], _bcc=[]):
        #update if the field value is vaild

        def set_value(name, param, value):
            if value is not None:
                if self._valid_email(value):
                    return value
                else:
                    self.logger.error("Invalid %s: %s address", name, value)

            return getattr(self, param)

        self._from = set_value('From', '_from', _from)
        self._to = set_value('To', '_to', _to)
        self._cc = set_value('CC', '_cc', _cc)
        self._bcc = set_value('BCC', '_bcc', _bcc)

    def send_email(self, subject='', content=''):

        self.logger.debug("From: %s\nTo: %s\nCC: %s\nBCC: %s\nSubject: %s\n",
                         self._from, self._to, self._cc, self._bcc, subject)

        self._smtp_setup()

        rcpt = map(lambda it: it.strip(), self._cc + self._bcc + self._to)

        msg = MIMEMultipart('alternative')
        msg['From'] = self._from
        msg['Subject'] = subject
        msg['To'] = ','.join(self._to)
        msg['Cc'] = ','.join(self._cc)
        msg['Bcc'] = ','.join(self._bcc)
        msg.attach(MIMEText(content))

        self.client_obj.sendmail(self._from, rcpt, msg.as_string())

        self._smtp_close()



