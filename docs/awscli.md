# Running the AWS CLI with JumpTheGun

To run the AWS CLI with JumpTheGun you must install the AWS CLI from source.
Note that this is supported, but is not the default installation method.


## Installing the AWS CLI from Source


### Notes

1. If you already have the AWS CLI installed, you'll likely want to uninstall
that version of it first, or install into an alternate location.

2. To install into an alternate location, use the `--prefix` flag when running
`./congigure` and/or the `DESTDIR` env var when running `make install`.
See [the official installation instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-source-install.html#source-getting-started-install-instructions)
for more details. 

3. You may set e.g. `PYTHON=/usr/local/bin/python3.11` for the `./configure`
command to use a specific version of Python.


### Prerequisites

1. Be able to run GNU Autotools generated files such as `configure` and
`Makefile`.  If Autotools is not already installed in your environment or you
need to update them, then follow the installation instructions found in
[How do I install the Autotools (as user)?](https://www.gnu.org/software/automake/faq/autotools-faq.html#How-do-I-install-the-Autotools-_0028as-user_0029_003f)
or [Basic Installation](https://www.gnu.org/savannah-checkouts/gnu/automake/manual/automake.html#Basic-Installation)
in the GNU documentation.

2. Have Python 3.8 or later installed.


### Installation

1. Download and extract the latest AWS CLI source tarball:
```shell
$ curl -o awscli.tar.gz https://awscli.amazonaws.com/awscli.tar.gz
$ tar -xzf awscli.tar.gz
```

2. Build:
```shell
$ cd awscli-*
$ ./configure --with-download-deps
$ make
```

3. Install:
```shell
$ make install
```

You may need to use `sudo` for this last command.

4. Test:
```shell
aws --version 
```


## Running with JumpTheGun

That hard part is over!  With JumpTheGun installed, run:
```shell
$ jumpthegun run aws ...
```

Note that a daemon will not yet be running for the first invocation, so it will
not be faster than normal.


## References

* [AWS Docs: Building and installing the AWS CLI from source](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-source-install.html)
