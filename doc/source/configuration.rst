=============
Configuration
=============

There is default configuration file ``config.yaml``, which can be used by the scripts.
If you wish to keep several configuration files, that is possible - just copy it and explicitly provide the name of it once you launch a script (``--config`` option).

Here is the description of available parameters in configuration file:

* **ssh** parameters of *SSH*

 * **opts** parameters to send to ssh command directly (recommended to leave at default)
 * **vars** environment variables to set for SSH

* **fuel_ip** the IP address of the master node in the environment
* **rqdir** the path of *rqdir*, the directory containing info about commands to execute and logs to gather
* **out-dir** directory to store output data
* **timeout** timeout for SSH commands in seconds
* **archives** directory to store the generated archives
* **log_files** path and filters for log files

Nodes which are stored in fuel database can be filtered by the following parameters:
 * roles,
 * online
 * status the list of statuses ex. ['ready', 'discover']
 * **node_ids** the list of ids, ex. [0,5,6]

* **hard_filter** hard filter for nodes
* **soft_filter** soft filters for nodes

Once you are done with the configuration, you might want to familiarize yourself with :doc:`Usage </usage>`.
