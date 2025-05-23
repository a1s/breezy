#! /usr/bin/env python3

# Copyright (C) 2007, 2008, 2009, 2017 Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""create_ssls.py -- create ssl keys and certificates for tests.

The https server requires at least a key and a certificate to start.

SSL keys and certificates are created with openssl which may not be available
everywhere we want to run the test suite.

To simplify test writing, the necessary keys and certificates are generated by
this script and used by the tests.

Since creating these test keys and certificates requires a good knowledge of
openssl and a lot of typing, we record all the needed parameters here.

Since this will be used rarely, no effort has been made to handle exotic
errors, the basic policy is that openssl should be available in the path and
the parameters should be correct, any error will abort the script. Feel free to
enhance that.

This script provides options for building any individual files or two options
to build the certificate authority files (--ca) or the server files (--server).
"""

import optparse
import os
import sys
from subprocess import PIPE, CalledProcessError, Popen

# We want to use the right breezy: the one we are part of
# FIXME: The following is correct but looks a bit ugly
_dir = os.path.dirname
our_bzr = _dir(_dir(_dir(_dir(os.path.realpath(__file__)))))
sys.path.insert(0, our_bzr)

import contextlib

from breezy.tests import ssl_certs


def error(s):
    print(s)
    exit(1)


def needs(request, *paths):
    """Errors out if the specified path does not exists."""
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        error(f"{request} needs: {','.join(missing)}")


def rm_f(path):
    """Rm -f path."""
    with contextlib.suppress(BaseException):
        os.unlink(path)


def _openssl(args, input=None):
    """Execute a command in a subproces feeding stdin with the provided input.

    :return: (returncode, stdout, stderr)
    """
    cmd = ["openssl"] + args
    proc = Popen(cmd, stdin=PIPE)
    (stdout, stderr) = proc.communicate(input.encode("utf-8"))
    if proc.returncode:
        # Basic error handling, all commands should succeed
        raise CalledProcessError(proc.returncode, cmd)
    return proc.returncode, stdout, stderr


ssl_params = {
    # Passwords
    "server_pass": "I will protect the communications",
    "server_challenge_pass": "Challenge for the CA",
    "ca_pass": "I am the authority for the whole... localhost",
    # CA identity
    "ca_country_code": "BZ",
    "ca_state": "Internet",
    "ca_locality": "Bazaar",
    "ca_organization": "Distributed",
    "ca_section": "VCS",
    "ca_name": "Master of certificates",
    "ca_email": "cert@no.spam",
    # Server identity
    "server_country_code": "LH",
    "server_state": "Internet",
    "server_locality": "LocalHost",
    "server_organization": "Testing Ltd",
    "server_section": "https server",
    "server_name": "127.0.0.1",  # Always accessed under that name
    "server_email": "https_server@localhost",
    "server_optional_company_name": "",
}


def build_ca_key():
    """Generate an ssl certificate authority private key."""
    key_path = ssl_certs.build_path("ca.key")
    rm_f(key_path)
    _openssl(
        ["genrsa", "-passout", "stdin", "-des3", "-out", key_path, "4096"],
        input=f"{ssl_params['ca_pass']}\n{ssl_params['ca_pass']}\n",
    )


def build_ca_certificate():
    """Generate an ssl certificate authority private key."""
    key_path = ssl_certs.build_path("ca.key")
    needs("Building ca.crt", key_path)
    cert_path = ssl_certs.build_path("ca.crt")
    rm_f(cert_path)
    _openssl(
        [
            "req",
            "-passin",
            "stdin",
            "-new",
            "-x509",
            # Will need to be generated again in 1000 years -- 20210106
            "-days",
            "365242",
            "-key",
            key_path,
            "-out",
            cert_path,
        ],
        input="{ca_pass}\n"
        "{ca_country_code}\n"
        "{ca_state}\n"
        "{ca_locality}\n"
        "{ca_organization}\n"
        "{ca_section}\n"
        "{ca_name}\n"
        "{ca_email}\n".format(**ssl_params),
    )


def build_server_key():
    """Generate an ssl server private key.

    We generates a key with a password and then copy it without password so
    that a server can use it without prompting.
    """
    key_path = ssl_certs.build_path("server_with_pass.key")
    rm_f(key_path)
    _openssl(
        ["genrsa", "-passout", "stdin", "-des3", "-out", key_path, "4096"],
        input=f"{ssl_params['server_pass']}\n{ssl_params['server_pass']}\n",
    )

    key_nopass_path = ssl_certs.build_path("server_without_pass.key")
    rm_f(key_nopass_path)
    _openssl(
        ["rsa", "-passin", "stdin", "-in", key_path, "-out", key_nopass_path],
        input=f"{ssl_params['server_pass']}\n",
    )


def build_server_signing_request():
    """Create a CSR (certificate signing request) to get signed by the CA."""
    key_path = ssl_certs.build_path("server_with_pass.key")
    needs("Building server.csr", key_path)
    server_csr_path = ssl_certs.build_path("server.csr")
    rm_f(server_csr_path)
    _openssl(
        ["req", "-passin", "stdin", "-new", "-key", key_path, "-out", server_csr_path],
        input="{server_pass}\n"
        "{server_country_code}\n"
        "{server_state}\n"
        "{server_locality}\n"
        "{server_organization}\n"
        "{server_section}\n"
        "{server_name}\n"
        "{server_email}\n"
        "{server_challenge_pass}\n"
        "{server_optional_company_name}\n".format(**ssl_params),
    )


def sign_server_certificate():
    """CA signs server csr."""
    server_csr_path = ssl_certs.build_path("server.csr")
    ca_cert_path = ssl_certs.build_path("ca.crt")
    ca_key_path = ssl_certs.build_path("ca.key")
    needs("Signing server.crt", server_csr_path, ca_cert_path, ca_key_path)
    server_cert_path = ssl_certs.build_path("server.crt")
    server_ext_conf = ssl_certs.build_path("server.extensions.cnf")
    rm_f(server_cert_path)
    _openssl(
        [
            "x509",
            "-req",
            "-passin",
            "stdin",
            # Will need to be generated again in 1000 years -- 20210106
            "-days",
            "365242",
            "-in",
            server_csr_path,
            "-CA",
            ca_cert_path,
            "-CAkey",
            ca_key_path,
            "-set_serial",
            "01",
            "-extfile",
            server_ext_conf,
            "-out",
            server_cert_path,
        ],
        input=f"{ssl_params['ca_pass']}\n",
    )


def build_ssls(name, options, builders):
    if options is not None:
        for item in options:
            builder = builders.get(item, None)
            if builder is None:
                error(f"{item} is not a known {name}")
            builder()


opt_parser = optparse.OptionParser(usage="usage: %prog [options]")
opt_parser.set_defaults(ca=False)
opt_parser.set_defaults(server=False)
opt_parser.add_option(
    "--ca", dest="ca", action="store_true", help="Generate CA key and certificate"
)
opt_parser.add_option(
    "--server",
    dest="server",
    action="store_true",
    help="Generate server key, certificate signing request and certificate",
)
opt_parser.add_option(
    "-k",
    "--key",
    dest="keys",
    action="append",
    metavar="KEY",
    help="generate a new KEY (several -k options can be specified)",
)
opt_parser.add_option(
    "-c",
    "--certificate",
    dest="certificates",
    action="append",
    metavar="CERTIFICATE",
    help="generate a new CERTIFICATE (several -c options can be specified)",
)
opt_parser.add_option(
    "-r",
    "--sign-request",
    dest="signing_requests",
    action="append",
    metavar="REQUEST",
    help="generate a new signing REQUEST (can be repeated)",
)
opt_parser.add_option(
    "-s",
    "--sign",
    dest="signings",
    action="append",
    metavar="SIGNING",
    help="generate a new SIGNING (several -s options can be specified)",
)


key_builders = {"ca": build_ca_key, "server": build_server_key}
certificate_builders = {"ca": build_ca_certificate}
signing_request_builders = {"server": build_server_signing_request}
signing_builders = {"server": sign_server_certificate}


if __name__ == "__main__":
    (Options, args) = opt_parser.parse_args()
    if Options.ca or Options.server:
        if (
            Options.keys
            or Options.certificates
            or Options.signing_requests
            or Options.signings
        ):
            error("--ca and --server can't be used with other options")
        # Handles --ca before --server so that both can be used in the same run
        # to generate all the files needed by the https test server
        if Options.ca:
            build_ca_key()
            build_ca_certificate()
        if Options.server:
            build_server_key()
            build_server_signing_request()
            sign_server_certificate()
    else:
        build_ssls("key", Options.keys, key_builders)
        build_ssls("certificate", Options.certificates, certificate_builders)
        build_ssls(
            "signing request", Options.signing_requests, signing_request_builders
        )
        build_ssls("signing", Options.signings, signing_builders)
