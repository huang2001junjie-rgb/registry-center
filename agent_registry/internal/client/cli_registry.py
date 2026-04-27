# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import argparse
import json
import sys

from agent_registry.internal.client.registry_client import RegistryClient


def main():
    parser = argparse.ArgumentParser(
        description="Registry Center Internal CLI Tool"
    )
    parser.add_argument(
        "action",
        choices=["approval"],
        help="Action to perform"
    )
    parser.add_argument(
        "--agent-name",
        required=True,
        help="Agent name"
    )
    parser.add_argument(
        "--organization",
        required=True,
        help="Organization name"
    )
    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="text",
        help="Output format"
    )
    
    args = parser.parse_args()
    
    client = RegistryClient()
    
    if args.action == "approval":
        result = client.approval_agent(args.agent_name, args.organization)
    
    if args.output == "json":
        print(json.dumps(result, indent=2))
    else:
        if result.get("success"):
            print(f"Success: {result.get('message', 'OK')}")
            if result.get("data"):
                print(f"Data: {json.dumps(result['data'], indent=2)}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            print(f"Message: {result.get('message', '')}")


if __name__ == "__main__":
    main()