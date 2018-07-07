import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jsonparser import JSONParser
import logging
import re
import pkg_resources

class Email(object):

    """
    Wrapper class for sending email.
    """

    def _smtp_setup(self):

        if self.smtp_server is None or not isinstance(self.smtp_server, basestring):
            self.logger.error("Invalid SMTP server %s", self.smtp_server)
            return False

        if not self.smtp_port > 0 or not isinstance(self.smtp_port, (int, long)):
            self.logger.error("Invalid SMTP port %s", str(self.smtp_port))
            return False

        self.smtp_obj = smtplib.SMTP(host=self.smtp_server, port=self.smtp_port)

        if self.auth is not None and self.auth in self.supported_auths:
            if self.auth == 'TLS':
                self.smtp_obj.starttls()

        if self.username is not None and self.password is not None:
            self.smtp_obj.login(self.username, self.password)

        self.logger.debug("SMTP Server Open():%s port:%d\n", self.smtp_server, self.smtp_port)

    def _smtp_close(self):
        self.smtp_obj.quit()
        self.logger.debug("SMTP Server Close()\n")

    def _valid_email(self, data):

        def valid(email):
            if re.match(r'(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)', email):
                return True

        if isinstance(data, list):
            for item in data:
                if not valid(item):
                    return False
            return True
        elif isinstance(data, str):
            if valid(data):
                return True

        return False


    def __init__(self, cfg=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)

        # SMTP server related param defaults.
        self.smtp_server = None
        self.smtp_port = 0
        self.supported_auths = ['TLS']
        self.auth = None
        self.username = None
        self.password = None

        # Config file related defaults.
        self.cfg_src = cfg
        self.cfg = None
        self.cfgobj = None
        self.smtp_obj = None
        self.schema = pkg_resources.resource_filename('kernel_libs', 'schemas/email-schema.json')

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
            self.logger.debug(self.cfgobj.print_cfg())

            self.set_header(self.cfg["from"], self.cfg["to"], self.cfg["cc"], self.cfg["bcc"])
            self.set_smtp(self.cfg["smtp-server"], self.cfg["smtp-port"],
                          self.cfg["smtp-authentication"], self.cfg["smtp-username"],
                          self.cfg["smtp-password"])


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
                if self._valid_email(param):
                    return value
            else:
                self.logger.error("Invalid %s: %s address", name, value)

            return getattr(self, param)

        self._from = set_value('From', '_from', _from)
        self._to = set_value('To', '_to', _to)
        self._cc = set_value('CC', '_cc', _cc)
        self._bcc = set_value('BCC', '_bcc', _bcc)

    def send_email(self, subject='', content=''):

        set_val = lambda x, y: getattr(self, y) if x is None or x == '' else x

        self.logger.info("From: %s\nTo: %s\nCC: %s\nBCC: %s\nSubject: %s\n",
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

        self.smtp_obj.sendmail(self._from, rcpt, msg.as_string())

        self._smtp_close()



