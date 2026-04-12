# Copyright 2026 Gregor von Laszewski
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
from cloudmesh.ai.monitor.command.cli import entry_point

def main():
    """Main entry point for the monitor command."""
    # entry_point is the create_cli factory
    cli = entry_point()
    cli()

def register(cli):
    """Register the monitor command with the provided click group."""
    # entry_point is the create_cli factory
    monitor_group = entry_point()
    cli.add_command(monitor_group)