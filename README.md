# TestSuite Wrapper for Avocado Framework Tests


## Overview:
This repository contains a wrapper script and configuration files to allow the user to set up the Avocado Test Framework and run a suite of tests to help verify the OpenPOWER Host OS and Guest Virtual Machine (VM) stability.

The tests are integrated into the avocado framework to increase the overall ease of use and to allow the open source community to easily add and run new tests within the suite.

See the [References](#references) section below for links to the avocado framework and avocado documentation.

----

## Operating System Support:
A PowerPC bare-metal system running OpenPOWER Host OS is required to execute any test suite in this repository (Host or Guest tests).

Guest test cases were validated against the following ppc64le guests:
* RHEL 8.0+
* RHEL 7.7+
* Fedora 29+
* Ubuntu 18.04+

Any Operating System that has python3 should be able to run this suite.

-----

## Prerequisites:
Python3 is installed on the System.

>Note : If python3 bin is not pointing to python binary in the system, please create of soft link of python pointing to python3.
>
> Example:
 `ln -s /usr/bin/python3 /usr/bin/python`

The `avocado-setup.py`script must always be run as root or as a user with root privileges or you risk permission denied errors.

The script will check your environment for tooling prerequisites and issue a warning/error if any prerequisites are not installed on the system and cannot be installed automatically.

------

### Guest VM Install Manual Prerequisites:
Before installing the Guest VM (`--install` option used), you must complete the following manual tasks:

1. Place the ISO image for the guest OS in the `isos/` folder. Download Fedora images and place them at the expected paths:
> `curl -o isos/Fedora-Server-DVD-ppc64le-29.iso https://archives.fedoraproject.org/pub/archive/fedora-secondary/releases/29/Server/ppc64le/iso/Fedora-Server-dvd-ppc64le-29-1.2.iso`
>
> Make sure you run `python avocado-setup.py --bootstrap` every time a new image is added or updated under `isos/` directory.Running bootstrap will copy all images to `data/avocado-vt/isos/linux/` directory.
>
> Note: This step is not required for CentOS guest Installation, as it would pick up automatically.

2. Open firewall ports 8000-8020. They are needed by the avocado test framework to host the kickstart file for the guest using the default bridge network. Suggested iptables command for RHEL distribution:
> `iptables -t filter -I INPUT -p tcp -m state --dport 8000:8020 --state NEW -j ACCEPT`

--------

### Script Usage Information:

It is highly recommended for users to execute the following command as root when running the test suite for the first time or you risk permission denied errors.  See the below information for details:
> `$ ./avocado-setup.py --run-suite host_sanity,guest_short_sanity --install`

#### Script help output:

```
$ ./avocado-setup.py -h
    usage: avocado-setup.py [-h] [--bootstrap] [--run-suite RUN_SUITE]
                            [--output-dir OUTPUTDIR] [--use-test-dir]
			    [--input-file INPUTFILE]
                            [--interval-time INTERVAL] [--verbose]
                            [--only-filter ONLY_FILTER] [--no-filter NO_FILTER]
                            [--additional-args ADD_ARGS] [--guest-os GUEST_OS]
                            [--vt {qemu,libvirt}] [--install] [--no-download]
                            [--no-deps-check] [--install-deps] [--clean]
                            [--enable-kvm]

    optional arguments:
      -h, --help            show this help message and exit
      --bootstrap           Prepare the environment for test
      --run-suite RUN_SUITE
                            Indicate which test suite(s) to run
      --output-dir OUTPUTDIR
                            Specify the custom test results directory
      --use-test-dir        Use corresponding test-name dir for storing job results
      --input-file INPUTFILE
                            Specify input file for custom mux values for host
                            tests
      --interval-time INTERVAL
                            Specify the interval time between tests
      --verbose             Enable verbose output on the console
      --only-filter ONLY_FILTER
                            Add filters to include specific avocado tests,features
                            from the guest test suite
      --no-filter NO_FILTER
                            Add filters to exclude specific avocado tests,features
                            from the guest test suite
      --additional-args ADD_ARGS
                            Pass additional arguments to the command
      --guest-os GUEST_OS   Provide Guest os: Default: JeOS.27.ppc64le
      --vt {qemu,libvirt}   Provide VT: qemu or libvirt Default: libvirt
      --install             Install the Guest VM, if needed.
      --no-download         To download the preinstalled guest image
      --no-deps-check       To force wrapper not to check for dependancy packages
      --install-deps        To force wrapper to install dependancy packages (Only
                            for Ubuntu, SLES and yum based OS)
      --clean               To remove/uninstall autotest, avocado from system
      --enable-kvm          enable bootstrap kvm tests

```

### Argument Details:
1. `--bootstrap`:

    > Use this option to bootstrap the environment so that all of the required repositories (avocado, avocado-vt, avocado-misc-tests) are downloaded, installed, and configured.
    >
    > Example command to bootstrap the test suite with only host tests.
    >
    > `./avocado-setup.py --bootstrap`
    >
    > Example command to bootstrap the test suite with guests tests.
    >
    > `./avocado-setup.py --bootstrap --enable-kvm`

2. `--run-suite RUN_SUITE`:

    >Use this option to reference one of the files in the config/tests/host/ or config/tests/guest/{libvirt, qemu} folders. The RUN_SUITE value must be prefixed based on which folder (guest or host) the config file is located in.  Multiple RUN_SUITE values must be separated by a comma.

    _Preconfigured possible RUN_SUITE values:_

    [_host_sanity_](config/tests/host/sanity.cfg):
    >
    >This file lists the specific scripts that are run from the Avocado Test Framework [avocado-misc-tests](https://github.com/avocado-framework-tests/avocado-misc-tests) repository.
    >
    > Example command to run the preconfigured Host OS test suite only:
    >
    > `./avocado-setup.py --run-suite host_sanity`

    [_guest_sanity_](config/tests/guest/libvirt/sanity.cfg):
    >
    >   This file runs a full series of regular and error injection tests against the specified guest VM using various virsh commands. This set of tests can take 4-5 hours to complete.  The "variants:" section of the config file shows which commands are tested.
    >
    > Example command to install a new Guest VM and run the preconfigured full guest test suite against it:
    >
    > `./avocado-setup.py --run-suite guest_sanity --install`

    [_guest_short_sanity_]( config/tests/guest/libvirt/short_sanity.cfg):

    > This file runs a shorter series of tests against the specified guest VM using various virsh commands. This set of tests can take 1-2 hours to complete.  The "variants:" section of the config file shows which commands are tested.
    >
    > Example command to install a new Guest VM and run the preconfigured short guest test suite against it:
    >
    > `./avocado-setup.py --run-suite guest_short_sanity --install`

    and many more configs, can be found under [_host_](config/tests/host) and [_guest_](config/tests/guest)


3. `--output-dir`:

    >Use this option to provide a custom directory for avocado test results. The avocado test results are stored in the /current_run_path/results folder by default.
    >
    >Example command to run the host and guest test suite and output the test results to the /tmp folder:
    >
    > `./avocado-setup.py --run-suite guest_sanity,host_sanity --output-dir /tmp`
    >
    > NOTE: The avocado-setup.py log will always be generated at /current_run_path/avocado-wrapper.log

4. `--use-test-dir`:
    >Use this option to store the avocado test results in directories corresponding to the test name.
    >
    > Example:
    >
    > `./avocado-setup.py --run-suite host_sched` --use-test-dir
    >
    > Results directory will contain directories with each test name
    > /current_path/results/<test_name_1>/<job-dir>/job.log
    >
    > NOTE: This option can be used with or without the --output-dir option

4. `--input-file`:
    >Use this option to specify input file for custom mux values for host tests. This is a config file format, with config section indicating the test cfg file name,
    and the key value pairs indicating the yaml parameter to be changed and its corresponding value, respectively.
    >
    >A key (yaml parameter to be changed) in an input file replaces the value (yaml parameter's value to be changed) of that yaml parameter's value in all the yaml files specified in that test cfg
    >
    >Example: Consider [example.cfg](config/tests/host/example.cfg)
    >
    >It contains 1 yaml file,namely [ioping.yaml](https://github.com/avocado-framework-tests/avocado-misc-tests/blob/master/io/disk/ioping.py.data/ioping.yaml)
    Now, it has yaml parameters like mode, count, deadline, period, disk, etc.
    Suppose user wants to change only 3 of those values, say disk, wsize and period, user can have that alone in our input file.
    Refer [input_example.txt](input_example.txt) for this example.
    Input file templates for host tests can be found at [_inputs_](config/inputs)


5. `--verbose`:
    > Use this option to display test verbose output on the console.
    >
    > Example command to install a new guest VM, run the full host & guest test suites, and display verbose output on the console:
    >
    > `./avocado-setup.py --run-suite guest_sanity,host_sanity --install --verbose`


6. `--only-filter`:
    >Use this option to add additional specific avocado tests or features to the guest test suite. This filter option is for advanced users of the avocado test framework who want to temporarily adjust the tests being run without having to create or change configuration files.
    >
    > Example command to run the host & guest test suites and add "virtio_scsi virtio_net qcow2" filter to the guest test suite:
    >
    > ./avocado-setup.py --run-suite guest_cpu,host_sanity --install --only-filter "virtio_scsi virtio_net qcow2"
    >
    > NOTE: Ensure you do not include a filter in the command that is a duplicate of a filter in the guest test suite being run.  This could cause avocado test errors.


7. `--no-filter`:
    > Use this option to remove specific avocado tests or features from the guest test suite. This filter option is for advanced users of the avocado test framework who want to temporarily adjust the tests being run without having to create or change configuration files.
    >
    > Example command to run the host & guest test suites and remove the "virtio_scsi" filter from the guest test suite:
    >
    > python avocado-setup.py --run-suite guest_sanity,host_sanity --install --no-filter "virtio_scsi"
    >
    > NOTE: Ensure you do not include a filter in the command that is a duplicate of a filter in the guest test suite being run.  This could cause avocado test errors.


8. `--additional-args`:
    > Use this option to pass any additional avocado arguments to run tests. A preconfigured set of Host or Guest VM tests has already been provided and will run based on the value chosen for `--run-suite`. This additional option is for advanced users of the avocado test framework who want to run additional tests within that framework.

9. `--guest-os`:
    > Use this option to specify the guest os for the guest tests to run against.
    >
    > By default, the value is JeOS.27.ppc64le.
    Supported Guests: JeOS.27.ppc64le, Fedora.31.ppc64le etc.,

10. `--vt {qemu or libvirt}`:
    > Use this option to choose either the libvirt or qemu folder when guest_sanity is the RUN_SUITE value.  By default, the libvirt folder is used.

11. `--install`:
    > Use this option to install the guest VM before or during the first time that you run any guest test suite.  Advanced avocado users may install their guest VM separately, but the install must follow the strict avocado configuration rules.
    >
    > NOTE: Complete all Guest VM Install prerequisites listed in the Prerequisites section above BEFORE running this script with the `--install` option.


12. `--no-download`:
    > Use this option to skip the guest image download. This helps to save time when you are using an already pre-installed guest VM image.


13. `--no-deps-check`:
    > Force wrapper to skip check for dependancy packages.  This helps to save time when re-running tests on a system where prereqs have already been checked once.

14. `--clean`:
    > Remove/Uninstall autotest and avocado from system after test completion.<br>
    >
    > USE IT WITH CAUTION: When this option used alone(i.e ./avocado-setup.py --clean), this will remove even the avocado config and data directory(includes guest images) and tests directoty.

15. `--enable-kvm`:
    > By default kvm(guest VM) tests environment is not bootstrapped, enable this flag to bootstrap KVM (guest VM) tests.


### Customizing Test Suites:

  The Host and Guest sanity suites were created to include a varied collection of tests to validate new Host OS installations.
  There are additional tests that were not included in the sanity suites that users can optionally add if they wish.

   _Adding Guest Sanity Tests:_

    You must be a proficient/advanced Avocado test suite user to correctly customize the Guest sanity suites since the syntax of these configuration files is very specific.

  _Adding Host Sanity Tests:_

     The Host sanity tests are listed in the config/tests/host/sanity.cfg file in this repository.  These are tests used directly
      from the avocado-misc-tests respository (see link in the REFERENCE LINKS section below).  If you want to run additional
      tests from this repository, simply add a new line in the sanity.cfg file with the location of the file within the
      avocado-misc-tests repository.

      For Example:
         - A user wishes to run ras.py test in the generic folder of the avocado-misc-tests repository. The purpose of this
         test is documented within the file itself.
         - The exact location of this test in the repository is "generic/ras.py".
         - The user downloads this tests repository onto their system and edits the config/tests/host/sanity.cfg file.
         - The user adds a line "avocado-misc-tests/generic/ras.py" (without the quotes) to the end of the config/tests/host/sanity.cfg
         file in this tests repository and saves the file.
         - The user runs the host_sanity suite using the avocado-setup.py script explained in Section 4 above.
         - If the user wishes to run a test with yaml file inputs, the yaml file can be specified in the same line in the cfg file,
         separated by a space. Refer config/tests/host/example.cfg for example.
         - If the user wishes to run a test with test-specific additional arguements such as --execution-order, --mux-filer-only etc.,
         those can be specified in the same line. Note that test-specific arguements can be provided with or without the yaml,
         followed by a space within quotes. Refer config/tests/host/example.cfg for example

--------

### No Run Test:
Some tests have the potential of causing system crashes / hangs. Such test in cfg file hinders the run of tests that follow.
So, if such tests are identified and need to be "not run" for a particular environment (Since they can run fine on others), we have a provision to mention such tests to not run.
> Please have a look at [config/wrapper/no_run_tests.conf](config/wrapper/no_run_tests.conf)

------

### Pre/Post Script support:
  User need to popluate their pre/post scripts as  prescript and postscript directory
  * Create a directory named `prescript` inside [config/](config/) directory  and populated with pre scripts
  * Create a directory named `postscript` inside [config/](config/) directory and populated with post scripts

-----

### References:
* [Avocado Test Framework](https://github.com/avocado-framework/avocado)
* [Avocado Test Framework documenation](http://avocado-framework.readthedocs.org)
* [Avocado Tests repository](https://github.com/avocado-framework-tests/avocado-misc-tests)
* [Avocado-vt Plugin for KVM](https://github.com/avocado-framework/avocado-vt)
* KVM Tests:
    [Qemu Test repository](https://github.com/autotest/tp-qemu),
    [Libvirt Test repository](https://github.com/autotest/tp-libvirt)

-----

### Known Issues and Limitation:
Refer to the [Issues](https://github.com/open-power-host-os/tests/issues?q=is%3Aopen+is%3Aissue) section of this repository for details on bugs, limitations, future enhancements, and investigations.

[Click](https://github.com/open-power-host-os/tests/issues/new) here to open new issue.
