import os
import time
import shutil
import threading

from socket import gethostname
from OpenSSL import crypto

from runner_service import configuration

import logging
logger = logging.getLogger(__name__)


class RunnerServiceError(Exception):
    pass


def fread(file_path):
    """ return the contents of the given file """
    with open(file_path, 'r') as file_fd:
        return file_fd.read().strip()


def create_self_signed_cert(cert_dir, cert_pfx):
    """
    Looks in cert_dir for the key files (using the cert_pfx name), and either
    returns if they exist, or create them if they're missing.
    """

    cert_filename = os.path.join(cert_dir,
                                 "{}.crt".format(cert_pfx))
    key_filename = os.path.join(cert_dir,
                                "{}.key".format(cert_pfx))

    logger.debug("Checking for the SSL keys in {}".format(cert_dir))
    if os.path.exists(cert_filename) \
            or os.path.exists(key_filename):
        logger.info("Using existing SSL files in {}".format(cert_dir))
        return (cert_filename, key_filename)
    else:
        logger.info("Existing SSL files not found in {}".format(cert_dir))
        logger.info("Self-signed cert will be created - expiring in {} "
                    "years".format(configuration.settings.cert_expiration))

        # create a key pair
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 1024)

        # create a self-signed cert
        cert = crypto.X509()
        cert.get_subject().C = "US"
        cert.get_subject().ST = "North Carolina"
        cert.get_subject().L = "Raliegh"
        cert.get_subject().O = "Red Hat"
        cert.get_subject().OU = "Ansible"
        cert.get_subject().CN = gethostname()
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)

        # define cert expiration period(years)
        cert.gmtime_adj_notAfter(configuration.settings.cert_expiration * 365 * 24 * 60 * 60)

        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha512')

        logger.debug("Writing crt file to {}".format(cert_filename))
        with open(os.path.join(cert_dir, cert_filename), "wt") as cert_fd:
            cert_fd.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode('utf-8'))

        logger.debug("Writing key file to {}".format(key_filename))
        with open(os.path.join(cert_dir, key_filename), "wt") as key_fd:
            key_fd.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode('utf-8'))

        return (cert_filename, key_filename)


class TimeOutLock(object):

    cond = threading.Condition(threading.Lock())

    def __init__(self, lock_object):
        self.mutex = lock_object

    def wait(self, timeout_secs):
        with TimeOutLock.cond:
            current_time = start_time = time.time()
            while current_time < start_time + timeout_secs:
                # try and acquire the lock, but don't block
                if self.mutex.acquire(False):
                    # got it!
                    return True
                else:
                    TimeOutLock.cond.wait(timeout_secs - current_time + start_time)
                    current_time = time.time()

        # timeout hit, couldn't acquire the lock in time
        return False

    def reset(self):
        self.mutex.release()
        try:
            TimeOutLock.cond.notify()
        except RuntimeError:
            # cond is not held by anyone
            pass


def rm_r(path):
    if not os.path.exists(path):
        return
    if os.path.isfile(path) or os.path.islink(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)
