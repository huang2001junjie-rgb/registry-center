# 注册中心内部交互服务设计文档

## 1. 功能概述

### 1.1 背景

注册中心系统(registry-center)作为多个Agent之间的中转站，需要与多个Agent进程进行交互。为了更好地管理内部交互操作，需要实现一个统一的内部交互服务，支持审核、配置、统计、查询等多种操作。

### 1.2 核心需求

#### 需求1：审核开关配置

- 用户可通过`python -m agent_registry.init`命令配置审核开关的开启状态
- 审核开关配置写入`etc/conf/server.conf`文件
- 审核开关开启后不能关闭（单向开关）

#### 需求2：Agent状态管理

- **审核开关开启时**：
  - Agent注册后初始状态为"已注册"
  - 调用审核接口后状态更新为"已发布"
  
- **审核开关关闭时**：
  - Agent注册后直接设置为"已发布"状态

#### 需求3：统一内部交互服务

- 通过UDS(Unix Domain Socket)实现内部交互能力
- 统一的socket文件入口：`/var/run/registry_center.sock`
- 支持多种内部交互操作（审核、配置、统计、查询等）
- 与HTTP服务在同一进程内运行（共享数据和配置）

#### 需求4：Handler扩展机制

- 采用Handler模式处理不同操作
- 每个操作有独立的Handler类
- 易于扩展新的内部交互功能

## 2. 系统设计

### 2.1 整体架构

#### 2.1.1 进程架构

```
┌─────────────────────────────────────────────────────┐
│ Registry Center 进程（单个进程）                      │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ 主线程：HTTP服务                              │   │
│  │                                             │   │
│  │  ├─ /rest/a2a-t/v1/agents/register          │   │
│  │  ├─ /rest/a2a-t/v1/agents/query             │   │
│  │  ├─ /rest/a2a-t/v1/agents/deregister        │   │
│  │  └─ ...其他HTTP接口                          │   │
│  │                                             │   │
│  │  监听：127.0.0.1:9301                        │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ 子线程：UDS服务（守护线程）                    │   │
│  │                                             │   │
│  │  RegistryCenterService                      │   │
│  │  ├─ 统一socket入口                           │   │
│  │  ├─ 请求分发器                               │   │
│  │  ├─ 权限检查器                               │   │
│  │  └─ Handler分发                             │   │
│  │                                             │   │
│  │  监听：/var/run/registry_center.sock         │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  共享资源：                                          │
│  ├─ RegistryCore实例（Agent数据）                   │
│  ├─ 配置文件（etc/conf/server.conf）               │
│  ├─ 数据文件（data/agentcard.json）                │
│  └─ 日志系统                                        │
└─────────────────────────────────────────────────────┘

启动命令：python -m agent_registry.start
停止：Ctrl+C 或 kill进程PID
```

#### 2.1.2 服务组件架构

```
┌─────────────────────────────────────────┐
│ RegistryCenterService (统一服务端)        │
│                                         │
│  监听：/var/run/registry_center.sock      │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 请求分发器        │   │
│  │ 根据action分发到不同handler       │   │
│  └─────────────┬───────────────────┘   │
│                │                        │
│      ┌─────────┴─────────┬──────┬─────┐│
│      │                   │      │     ││
│      ▼                   ▼      ▼     ▼│
│  ┌────────┐  ┌────────┐ ┌────┐ ┌────┐ │
│  │审核    │  │配置    │ │统计│ │查询│ │
│  │Handler │  │Handler │ │Hdlr│ │Hdlr│ │
│  └────────┘  └────────┘ └────┘ └────┘ │
│                                         │
│  后续可扩展：注销Handler、重置Handler等    │
└─────────────────────────────────────────┘

                    ↓ UDS连接

┌──────────────────┐
│ RegistryClient    │
│ (统一客户端)       │
│                  │
│ 发送请求：         │
│ {                │
│  "action":"audit",│ ← action字段区分操作
│  "agent_name":"X",│
│  "organization":"Y"│
│ }                │
└──────────────────┘
```

### 2.2 审核开关配置

#### 2.2.1 配置项

在`etc/conf/server.conf`文件中新增配置项：

```ini
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.

# HTTP服务配置
ip=127.0.0.1
port=9301

# Agent审核功能开关
agent_audit_enabled=true

# UDS服务配置
uds_service_enabled=true
uds_socket_path=/var/run/registry_center.sock
uds_socket_permissions=660
uds_socket_gid=1000

# 其他配置...
ssl_certfile=etc/ssl/server.cer
ssl_keyfile=etc/ssl/server_key.pem
```

**配置说明：**

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `agent_audit_enabled` | Agent审核功能开关 | `false` |
| `uds_service_enabled` | UDS服务开关 | `true` |
| `uds_socket_path` | UDS socket文件路径 | `/var/run/registry_center.sock` |
| `uds_socket_permissions` | socket文件权限 | `660` (rw-rw----) |
| `uds_socket_gid` | socket文件组ID | `1000` (registry_group) |

**重要说明：**

- UDS服务**没有端口概念**，只有socket文件路径
- socket文件路径相当于TCP/IP的"端口"
- socket文件权限决定谁可以访问

#### 2.2.2 配置流程

```
┌─────────────────────────────────┐
│  执行: python -m agent_registry.init │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  读取现有配置                     │
│  agent_audit_enabled=?          │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  提示用户输入审核开关配置         │
│  "是否开启审核功能 (y/n, 默认: false)" │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  用户输入: y/n                   │
└──────────┬──────────────────────┘
           │
      ┌────┴────┐
      │         │
  输入y      输入n
      │         │
      │         ▼
      │  ┌──────────────────────┐
      │  │ 检查现有配置           │
      │  │ agent_audit_enabled=? │
      │  └─────────┬────────────┘
      │       ┌────┴────┐
      │       │         │
      │    现有=true  现有=false
      │       │         │
      │       ▼         ▼
      │  ┌─────────┐  ┌─────────┐
      │  │报错：不能│  │允许关闭 │
      │  │关闭审核  │  │→开启审核│
      │  └─────────┘  └─────────┘
      │
      ▼
┌─────────────────────────────────┐
│  写入配置到server.conf            │
│  agent_audit_enabled=true        │
│  uds_service_enabled=true        │
│  uds_socket_path=...             │
└─────────────────────────────────┘
```

#### 2.2.3 配置变更规则

**规则1：审核开关开启后不能关闭**

```python
# 现有配置: agent_audit_enabled=true
# 用户输入: n (尝试关闭)

# 系统报错：
错误：审核功能已开启，不能关闭！
原因：已存在"已注册"状态的Agent，关闭审核会导致状态不一致。

建议：
1. 保持审核功能开启状态
2. 或先处理所有"已注册"状态的Agent
```

**规则2：审核开关关闭后可以开启**

```python
# 现有配置: agent_audit_enabled=false
# 用户输入: y (尝试开启)

# 系统允许：
配置成功：审核功能已开启
注意：
- 新注册的Agent初始状态为"已注册"
- 已存在的"已发布"状态Agent保持不变
```

### 2.3 Agent状态模型

#### 2.3.1 状态定义

Agent状态分为两种：

| 状态 | 说明 | 可执行操作 |
|------|------|-----------|
| `registered` | 已注册 | 等待审核、可被审核接口调用 |
| `published` | 已发布 | 可被查询、可被调用、可被注销 |

#### 2.3.2 状态转换

```
┌─────────────────┐
│  Agent注册请求   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  检查审核开关配置                 │
│  agent_audit_enabled=?          │
└────────┬────────────────────────┘
         │
    ┌────┴────┐
    │         │
  true      false
    │         │
    ▼         ▼
┌──────────┐ ┌──────────┐
│状态=已注册│ │状态=已发布│
└─────┬────┘ └──────────┘
      │
      │ 审核接口调用
      ▼
┌──────────────┐
│ 检查审核开关  │
│ agent_audit_enabled=? │
└───────┬──────┘
    ┌───┴───┐
    │       │
  true    false
    │       │
    ▼       ▼
┌──────────┐ ┌──────────┐
│状态=已发布│ │报错：审核│
│(审核成功)│ │功能已关闭│
└──────────┘ └──────────┘
```

#### 2.3.3 数据模型变更

**修改AgentCard数据结构：**

在AgentCard中新增`status`字段：

```json
{
  "name": "TestAgent",
  "provider": {
    "organization": "TestOrg",
    "url": "https://test.org"
  },
  "description": "Test Description",
  "url": "https://agent.test",
  "version": "1.0.0",
  "status": "registered",  // 新增字段：registered 或 published
  ...
}
```

**状态字段说明：**
- `status`：字符串类型，枚举值为 `"registered"` 或 `"published"`
- 默认值：根据审核开关配置决定
- 必填字段

### 2.4 UDS协议设计

#### 2.4.1 UDS vs TCP/IP对比

**关键区别：**

| 特性 | TCP/IP Socket | UDS Socket |
|------|--------------|------------|
| **地址** | IP地址 + 端口号 | 文件路径 |
| **跨机器** | 支持 | 不支持（只能本机） |
| **防火墙** | 需要配置端口规则 | 无需配置 |
| **配置项** | `ip + port` | `uds_socket_path` |
| **网络暴露** | 暴露到网络 | 不暴露（本地） |
| **权限控制** | 需要额外认证 | 文件权限自动控制 |

**UDS的"端口"就是"socket文件路径"：**

```ini
# HTTP服务：需要IP和端口
ip=127.0.0.1        # IP地址
port=9301           # 端口号

# UDS服务：只需要socket文件路径（相当于"端口")
uds_socket_path=/var/run/registry_center.sock  # socket路径（"端口"）
```

#### 2.4.2 UDS通信原理

**重要概念澄清：**

Socket文件不是数据存储文件，而是**通信端点标识**。

```
                    Socket文件
                    (通信端点标识)
                        
服务端                        客户端
  |                            |
  | 监听（等待连接）            | 连接（发起请求）
  |                            |
  | ←←←←←←←←←←←←←←←←←←←←←←←←←← |
  |      建立连接通道           |
  |                            |
  | ←←←← 接收请求              | 发送请求 →→→→
  |                            |
  | →→→→ 发送响应              | 接收响应 ←←←←
  |                            |
  v                            v

数据流在内核的socket缓冲区传输，不经过文件系统！
```

**数据传输过程：**

```
┌──────────────────┐
│ 客户端内存        │
│ request = "审核请求" │
└─────────┬────────┘
          │
          │ client_socket.send(request)
          │ 数据进入内核的socket缓冲区
          │
          ▼
┌──────────────────────────┐
│ 内核socket缓冲区           │ ← 数据在这里传输
│ (内存中的管道)             │   不写入文件系统！
└─────────┬────────────────┘
          │
          │ server_socket.recv()
          │ 数据从缓冲区读取到服务端内存
          │
          ▼
┌──────────────────┐
│ 服务端内存        │
│ request = "审核请求" │
└──────────────────┘
```

**验证：**

```bash
# 查看socket文件
ls -la /var/run/registry_center.sock

# 输出：
srw-rw---- 1 root registry_group 0 Jan 1 12:00 ...
# 注意：文件大小为0！数据不写入文件！

# 发送请求后再次查看
ls -la /var/run/registry_center.sock

# 输出：
srw-rw---- 1 root registry_group 0 Jan 1 12:00 ...
# 文件大小仍然是0！
```

#### 2.4.3 请求协议

**请求格式：**

```json
{
  "action": "audit",           // 操作类型（必填）
  "agent_name": "TestAgent",    // Agent名称（审核操作必填）
  "organization": "TestOrg"     // 组织名称（审核操作必填）
}
```

**不同操作的请求示例：**

```json
// 审核Agent
{
  "action": "audit",
  "agent_name": "TestAgent",
  "organization": "TestOrg"
}

// 更新配置
{
  "action": "config",
  "config_key": "audit_enabled",
  "config_value": "true"
}

// 查询统计
{
  "action": "stats",
  "type": "agent_count"
}

// 查询Agent
{
  "action": "query",
  "agent_name": "TestAgent",
  "organization": "TestOrg"
}
```

#### 2.4.4 响应协议

**成功响应格式：**

```json
{
  "success": true,
  "message": "Agent audit successful",
  "data": {
    "agent_name": "TestAgent",
    "organization": "TestOrg",
    "status": "published"
  }
}
```

**失败响应格式：**

```json
{
  "success": false,
  "error": "Agent not found",
  "message": "Cannot find agent: TestAgent (TestOrg)"
}
```

### 2.5 注册接口变更

#### 2.5.1 接口定义

**接口路径：** `/rest/a2a-t/v1/agents/register`

**请求体：** AgentCard JSON格式

**响应：**

```json
{
  "success": true,
  "message": "Agent registered successfully",
  "status": "registered",  // 或 "published"
  "agent": {
    "name": "TestAgent",
    "provider": {
      "organization": "TestOrg",
      "url": "https://test.org"
    },
    ...
  }
}
```

#### 2.5.2 注册流程

```python
async def register_agent(agent_card: ValidatedAgentCard):
    # 步骤1：验签（如果验签开关开启）
    if signature_validation_enabled:
        # 验签逻辑...
    
    # 步骤2：读取审核开关配置
    audit_enabled = config.get('agent_audit_enabled', 'false')
    
    # 步骤3：设置Agent初始状态
    if audit_enabled == 'true':
        agent_card.status = 'registered'  # 已注册，等待审核
    else:
        agent_card.status = 'published'   # 已发布，无需审核
    
    # 步骤4：保存Agent
    registry.register(agent_card)
    
    # 步骤5：返回响应
    return {
        "success": true,
        "status": agent_card.status,
        "message": f"Agent registered as {agent_card.status}"
    }
```

## 3. 实现方案

### 3.1 文件结构

```
registry-center/
├── agent_registry/
│   ├── internal/                     # 内部交互服务
│   │   ├── __init__.py
│   │   ├── registry_service.py       # 统一UDS服务端
│   │   ├── permission_checker.py     # 权限检查器
│   │   │
│   │   ├── handlers/                 # 操作处理器
│   │   │   ├── __init__.py
│   │   │   ├── base_handler.py       # Handler基类
│   │   │   ├── audit_handler.py      # 审核处理器
│   │   │   ├── config_handler.py     # 配置处理器（后续扩展）
│   │   │   ├── stats_handler.py      # 统计处理器（后续扩展）
│   │   │   ├── query_handler.py      # 查询处理器（后续扩展）
│   │   │   └── deregister_handler.py # 注销处理器（后续扩展）
│   │   │
│   │   ├── client/                   # 客户端
│   │   │   ├── __init__.py
│   │   │   ├── registry_client.py    # 统一客户端类
│   │   │   └── cli_registry.py       # 命令行工具
│   │   │
│   │   └── protocols/                # 协议定义
│   │       ├── __init__.py
│   │       ├── request.py            # 请求协议
│   │       ├── response.py           # 响应协议
│   │       └── actions.py            # action定义
│   │
│   ├── init.py                       # 配置初始化（新增审核开关）
│   ├── server.py                     # HTTP服务（修改注册接口）
│   ├── start.py                      # 启动脚本（启动UDS线程）
│   ├── core.py                       # 核心逻辑（新增状态管理）
│   │
│   └── model/
│       └── validated_agentcard.py    # 新增status字段验证
│
├── etc/
│   └── conf/
│       └── server.conf               # 配置文件
│
├── data/
│   └── agentcard.json                # Agent数据（新增status字段）
│
└── docs/
    └── internal_service_design.md    # 本设计文档
```

### 3.2 核心代码实现

#### 3.2.1 start.py - 启动脚本

```python
# agent_registry/start.py
import threading
import uvicorn
from loguru import logger

from agent_registry.server import app
from agent_registry.internal.registry_service import RegistryCenterService
from common.util.config_util import get_conf

def start_uds_service_thread():
    """启动UDS服务线程（守护线程）"""
    config = get_conf()
    
    # 检查UDS服务开关
    uds_enabled = config.get('uds_service_enabled', 'true')
    if uds_enabled != 'true':
        logger.info("UDS service is disabled")
        return
    
    # 获取socket配置
    socket_path = config.get('uds_socket_path', '/var/run/registry_center.sock')
    socket_perms = int(config.get('uds_socket_permissions', '660'), 8)
    socket_gid = int(config.get('uds_socket_gid', '1000'))
    
    # 创建UDS服务
    uds_service = RegistryCenterService(
        socket_path=socket_path,
        socket_permissions=socket_perms,
        socket_gid=socket_gid
    )
    
    # 启动服务
    uds_service.start()

def main():
    """启动注册中心"""
    config = get_conf()
    
    # 启动UDS服务线程（守护线程）
    uds_thread = threading.Thread(
        target=start_uds_service_thread,
        daemon=True,  # 守护线程：主进程退出时自动退出
        name="UDS-Service"
    )
    uds_thread.start()
    logger.info("UDS service thread started")
    
    # 启动HTTP服务（主线程）
    logger.info("Starting HTTP service...")
    uvicorn.run(
        app,
        host=config.get('ip', '127.0.0.1'),
        port=int(config.get('port', 9301))
    )

if __name__ == "__main__":
    main()
```

**进程结构说明：**

```
进程启动：python -m agent_registry.start

┌─────────────────────────────────────────┐
│ PID: 12345 (单个进程)                     │
│                                         │
│ 线程1（主线程）                           │
│ ├─ HTTP服务                              │
│ ├─ uvicorn.run()                         │
│ └─ 监听 127.0.0.1:9301                   │
│                                         │
│ 线程2（守护线程）                         │
│ ├─ UDS服务                               │
│ ├─ RegistryCenterService.start()         │
│ └─ 监听 /var/run/registry_center.sock    │
│                                         │
│ 线程3-N（请求处理线程）                    │
│ ├─ HTTP请求处理                          │
│ └─ UDS请求处理                           │
│                                         │
│ 共享资源：                                │
│ ├─ RegistryCore实例                      │
│ ├─ 配置文件                              │
│ └─ 日志系统                              │
└─────────────────────────────────────────┘
```

#### 3.2.2 registry_service.py - UDS服务端

```python
# agent_registry/internal/registry_service.py
import socket
import os
import json
import threading
from loguru import logger

from agent_registry.registry_instance import get_registry
from agent_registry.internal.handlers import get_handlers
from agent_registry.internal.permission_checker import PermissionChecker

class RegistryCenterService:
    """注册中心内部交互服务（统一UDS入口）"""
    
    def __init__(
        self,
        socket_path: str = '/var/run/registry_center.sock',
        socket_permissions: int = 0o660,
        socket_gid: int = 1000
    ):
        self.socket_path = socket_path
        self.socket_permissions = socket_permissions
        self.socket_gid = socket_gid
        self.registry = get_registry()
        self.handlers = get_handlers()
        self.permission_checker = PermissionChecker()
    
    def start(self):
        """启动UDS服务"""
        try:
            # 创建UDS socket
            server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            
            # 删除旧socket文件
            try:
                os.unlink(self.socket_path)
            except FileNotFoundError:
                pass
            
            # 绑定socket到文件路径
            server_socket.bind(self.socket_path)
            
            # 设置文件权限（访问控制）
            os.chmod(self.socket_path, self.socket_permissions)
            try:
                os.chown(self.socket_path, 0, self.socket_gid)
            except PermissionError:
                logger.warning("Cannot set socket group owner (need root)")
            
            # 开始监听
            server_socket.listen(5)
            
            logger.info(f"UDS service started on {self.socket_path}")
            logger.info(f"Socket permissions: {oct(self.socket_permissions)}")
            
            # 接收连接（无限循环）
            while True:
                conn, _ = server_socket.accept()
                
                # 处理请求（新线程）
                thread = threading.Thread(
                    target=self._handle_request,
                    args=(conn,),
                    daemon=True
                )
                thread.start()
                
        except Exception as e:
            logger.error(f"UDS service error: {e}")
            raise
    
    def _handle_request(self, conn):
        """处理单个请求"""
        try:
            # 接收请求
            data = conn.recv(4096)
            if not data:
                conn.close()
                return
            
            request = json.loads(data.decode('utf-8'))
            action = request.get('action')
            
            logger.info(f"Received UDS request: action={action}")
            
            # 检查action是否存在
            if not action:
                self._send_error(conn, "Missing action field")
                return
            
            # 权限验证（可选）
            # creds = self._get_peer_credentials(conn)
            # if not self.permission_checker.check(action, creds):
            #     self._send_error(conn, f"Permission denied for action: {action}")
            #     return
            
            # 分发到对应的handler
            handler = self.handlers.get(action)
            if not handler:
                self._send_error(conn, f"Unknown action: {action}")
                return
            
            # 执行操作
            response = handler.handle(request)
            
            # 发送响应
            conn.send(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            logger.error(f"UDS request handling error: {e}")
            self._send_error(conn, str(e))
        
        finally:
            conn.close()
    
    def _send_error(self, conn, error_message: str):
        """发送错误响应"""
        response = {
            "success": False,
            "error": error_message
        }
        conn.send(json.dumps(response).encode('utf-8'))
```

#### 3.2.3 base_handler.py - Handler基类

```python
# agent_registry/internal/handlers/base_handler.py
class BaseHandler:
    """Handler基类"""
    
    def handle(self, request: dict) -> dict:
        """
        处理请求
        
        Args:
            request: 请求内容
        
        Returns:
            dict: 响应内容
        """
        raise NotImplementedError("Subclasses must implement handle()")
    
    def validate_request(self, request: dict) -> bool:
        """验证请求参数"""
        return True
```

#### 3.2.4 audit_handler.py - 审核处理器

```python
# agent_registry/internal/handlers/audit_handler.py
from agent_registry.internal.handlers.base_handler import BaseHandler
from agent_registry.registry_instance import get_registry
from agent_registry.internal.handlers import get_handlers
from common.util.config_util import get_conf

class AuditHandler(BaseHandler):
    """审核处理器"""
    
    def __init__(self):
        self.registry = get_registry()
        self.config = get_conf()
    
    def handle(self, request: dict) -> dict:
        """处理审核请求"""
        
        # 检查审核开关
        audit_enabled = self.config.get('agent_audit_enabled', 'false')
        if audit_enabled != 'true':
            return {
                "success": False,
                "error": "Audit function is disabled"
            }
        
        # 获取参数
        agent_name = request.get('agent_name')
        organization = request.get('organization')
        
        if not agent_name or not organization:
            return {
                "success": False,
                "error": "Missing required parameters: agent_name or organization"
            }
        
        # 查找Agent
        agent = self.registry.get_by_key(agent_name, organization)
        if not agent:
            return {
                "success": False,
                "error": "Agent not found"
            }
        
        # 检查状态
        if agent.status == 'published':
            return {
                "success": False,
                "error": "Agent already published"
            }
        
        # 更新状态为已发布
        agent.status = 'published'
        self.registry.update(agent_name, organization, agent.model_dump())
        
        return {
            "success": True,
            "message": "Agent audit successful",
            "data": {
                "agent_name": agent_name,
                "organization": organization,
                "status": "published"
            }
        }
```

#### 3.2.5 handlers/__init__.py - Handler注册

```python
# agent_registry/internal/handlers/__init__.py
from agent_registry.internal.handlers.audit_handler import AuditHandler
# 后续扩展时导入其他Handler
# from agent_registry.internal.handlers.config_handler import ConfigHandler
# from agent_registry.internal.handlers.stats_handler import StatsHandler
# from agent_registry.internal.handlers.query_handler import QueryHandler

def get_handlers() -> dict:
    """获取所有handler"""
    return {
        "audit": AuditHandler(),
        # 后续扩展时添加新的handler
        # "config": ConfigHandler(),
        # "stats": StatsHandler(),
        # "query": QueryHandler(),
    }
```

#### 3.2.6 registry_client.py - 统一客户端

```python
# agent_registry/internal/client/registry_client.py
import socket
import json

class RegistryClient:
    """注册中心内部交互客户端"""
    
    SOCKET_PATH = "/var/run/registry_center.sock"
    
    def _call_action(self, action: str, params: dict) -> dict:
        """
        调用内部交互操作
        
        Args:
            action: 操作名称
            params: 操作参数
        
        Returns:
            dict: 响应内容
        """
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        
        try:
            # 连接UDS socket
            client_socket.connect(self.SOCKET_PATH)
            
            # 构造请求
            request = {"action": action, **params}
            
            # 发送请求
            client_socket.send(json.dumps(request).encode('utf-8'))
            
            # 接收响应
            response = client_socket.recv(4096)
            return json.loads(response.decode())
            
        except PermissionError:
            return {
                "success": False,
                "error": "Permission denied"
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "UDS service not running"
            }
        finally:
            client_socket.close()
    
    def audit_agent(self, agent_name: str, organization: str) -> dict:
        """审核Agent"""
        return self._call_action("audit", {
            "agent_name": agent_name,
            "organization": organization
        })
    
    # 后续扩展时添加新的方法
    # def update_config(self, config_key: str, config_value: str) -> dict:
    #     """更新配置"""
    #     return self._call_action("config", {
    #         "config_key": config_key,
    #         "config_value": config_value
    #     })
```

#### 3.2.7 cli_registry.py - 命令行工具

```python
# agent_registry/internal/client/cli_registry.py
import sys
import json
from agent_registry.internal.client.registry_client import RegistryClient

def main():
    """命令行工具入口"""
    if len(sys.argv) < 2:
        print("Usage: python -m agent_registry.internal.client.cli_registry <action> [args]")
        print("Actions:")
        print("  audit <agent_name> <organization>  - Audit an agent")
        # 后续扩展时添加新的命令
        # print("  config <key> <value>              - Update config")
        # print("  stats <type>                       - Get statistics")
        sys.exit(1)
    
    client = RegistryClient()
    action = sys.argv[1]
    
    if action == "audit":
        if len(sys.argv) < 4:
            print("Usage: audit <agent_name> <organization>")
            sys.exit(1)
        
        agent_name = sys.argv[2]
        organization = sys.argv[3]
        result = client.audit_agent(agent_name, organization)
    
    # 后续扩展时添加新的命令处理
    # elif action == "config":
    #     ...
    
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
    
    # 输出结果
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

**使用方式：**

```bash
# 审核Agent
python -m agent_registry.internal.client.cli_registry audit TestAgent TestOrg

# 输出：
{
  "success": true,
  "message": "Agent audit successful",
  "data": {
    "agent_name": "TestAgent",
    "organization": "TestOrg",
    "status": "published"
  }
}
```

#### 3.2.8 init.py - 配置初始化

```python
# agent_registry/init.py (新增审核开关配置)

class InitCommand:
    def init_command(self):
        # ... 原有配置逻辑 ...
        
        # 新增：审核功能开关配置
        default_audit_enabled = self.existing_config.get('agent_audit_enabled', 'false')
        current_audit_enabled = default_audit_enabled
        
        # 检查现有配置
        if current_audit_enabled == 'true':
            print("⚠️  注意：审核功能已开启，不能关闭！")
            audit_input = 'y'  # 强制保持开启
        else:
            audit_input = input(
                f"是否开启审核功能 agent_audit_enabled (y/n, 默认: {default_audit_enabled}): "
            ).strip().lower()
        
        # 处理用户输入
        if audit_input == 'n':
            if current_audit_enabled == 'true':
                print("❌ 错误：审核功能已开启，不能关闭！")
                print("   原因：已存在'已注册'状态的Agent")
                sys.exit(1)
            config['agent_audit_enabled'] = 'false'
        elif audit_input == 'y':
            config['agent_audit_enabled'] = 'true'
        else:
            config['agent_audit_enabled'] = default_audit_enabled
        
        # UDS服务配置
        config['uds_service_enabled'] = 'true'
        config['uds_socket_path'] = '/var/run/registry_center.sock'
        config['uds_socket_permissions'] = '660'
        
        self.save_config_to_file(config)
```

#### 3.2.9 server.py - 注册接口修改

```python
# agent_registry/server.py

@app.post("/rest/a2a-t/v1/agents/register")
async def register_agent(agent: ValidatedAgentCard, request: Request):
    """注册Agent"""
    
    # 验签逻辑（如果开启）...
    
    # 读取审核开关配置
    audit_enabled = config.get('agent_audit_enabled', 'false')
    
    # 设置Agent初始状态
    if audit_enabled == 'true':
        agent.status = 'registered'  # 已注册，等待审核
        status_message = "Agent registered, waiting for audit"
    else:
        agent.status = 'published'   # 已发布，无需审核
        status_message = "Agent registered and published"
    
    # 注册Agent
    result = await _perform_registration(agent, registry, client_ip, details)
    
    # 返回响应
    return JSONResponse(
        content={
            "success": result,
            "status": agent.status,
            "message": status_message
        },
        status_code=status.HTTP_201_CREATED
    )
```

#### 3.2.10 validated_agentcard.py - 状态字段验证

```python
# agent_registry/model/validated_agentcard.py

class ValidatedAgentCard(AgentCard):
    """验证后的AgentCard"""
    
    # 新增状态字段
    status: Optional[str] = Field(
        default='published',
        description="Agent状态: registered(已注册) 或 published(已发布)"
    )
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ['registered', 'published']:
            raise ValueError('状态仅支持 registered 或 published')
        return v
```

### 3.3 配置管理

#### 3.3.1 配置文件示例

```ini
# etc/conf/server.conf

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.

# HTTP服务配置
ip=127.0.0.1
port=9301

# Agent审核功能开关
agent_audit_enabled=true

# UDS服务配置
uds_service_enabled=true
uds_socket_path=/var/run/registry_center.sock
uds_socket_permissions=660
uds_socket_gid=1000

# 其他配置...
ssl_certfile=etc/ssl/server.cer
ssl_keyfile=etc/ssl/server_key.pem
signature_validation_enabled=true
```

#### 3.3.2 配置说明

| 配置项 | 说明 | 类型 | 默认值 |
|--------|------|------|--------|
| `ip` | HTTP服务IP | string | `127.0.0.1` |
| `port` | HTTP服务端口 | int | `9301` |
| `agent_audit_enabled` | 审核功能开关 | string | `false` |
| `uds_service_enabled` | UDS服务开关 | string | `true` |
| `uds_socket_path` | UDS socket路径 | string | `/var/run/registry_center.sock` |
| `uds_socket_permissions` | socket权限 | string | `660` |
| `uds_socket_gid` | socket组ID | int | `1000` |

**重要说明：**

- HTTP服务有`ip`和`port`（网络配置）
- UDS服务只有`uds_socket_path`（文件路径，没有端口概念）
- socket路径相当于TCP/IP的"端口"

### 3.4 数据持久化

#### 3.4.1 Agent数据格式

**data/agentcard.json：**

```json
[
  {
    "name": "TestAgent",
    "provider": {
      "organization": "TestOrg",
      "url": "https://test.org"
    },
    "description": "Test Description",
    "url": "https://agent.test",
    "version": "1.0.0",
    "status": "registered",  // 新增字段
    "skills": [...],
    ...
  },
  {
    "name": "AnotherAgent",
    "provider": {
      "organization": "AnotherOrg",
      "url": "https://another.org"
    },
    "status": "published",  // 新增字段
    ...
  }
]
```

#### 3.4.2 状态兼容性处理

```python
# agent_registry/core.py

def _load(self):
    """加载Agent数据"""
    data_list = load_from_file(self.persistence_file)
    
    for item in data_list:
        try:
            # 兼容处理：如果没有status字段，默认为published
            if 'status' not in item:
                item['status'] = 'published'
                logger.info(f"Agent {item['name']} missing status, set to published")
            
            agent = AgentCard(**item)
            key = self._make_key(agent.name, agent.provider.organization)
            self._agents[key] = agent
        except Exception as e:
            logger.error(f"Failed to load agent: {e}")
```

## 4. 扩展机制

### 4.1 Handler扩展

**添加新操作的步骤：**

#### 步骤1：创建新的Handler类

```python
# agent_registry/internal/handlers/deregister_handler.py

class DeregisterHandler(BaseHandler):
    """注销处理器"""
    
    def handle(self, request: dict) -> dict:
        """处理注销请求"""
        agent_name = request.get('agent_name')
        organization = request.get('organization')
        
        # 注销逻辑...
        
        return {
            "success": True,
            "message": "Agent deregistered"
        }
```

#### 步骤2：注册Handler

```python
# agent_registry/internal/handlers/__init__.py

from agent_registry.internal.handlers.deregister_handler import DeregisterHandler

def get_handlers() -> dict:
    return {
        "audit": AuditHandler(),
        "deregister": DeregisterHandler(),  # 新增
        # ...
    }
```

#### 步骤3：客户端添加方法

```python
# agent_registry/internal/client/registry_client.py

class RegistryClient:
    def deregister_agent(self, agent_name: str, organization: str) -> dict:
        """注销Agent"""
        return self._call_action("deregister", {
            "agent_name": agent_name,
            "organization": organization
        })
```

#### 步骤4：命令行添加命令

```python
# agent_registry/internal/client/cli_registry.py

elif action == "deregister":
    agent_name = sys.argv[2]
    organization = sys.argv[3]
    result = client.deregister_agent(agent_name, organization)
```

### 4.2 扩展示例

**后续可扩展的操作：**

| Action | Handler | 功能 |
|--------|---------|------|
| `audit` | AuditHandler | 审核Agent |
| `config` | ConfigHandler | 配置管理 |
| `stats` | StatsHandler | 统计查询 |
| `query` | QueryHandler | Agent查询 |
| `deregister` | DeregisterHandler | 注销Agent |
| `reset` | ResetHandler | 重置状态 |
| `batch_audit` | BatchAuditHandler | 批量审核 |

## 5. 测试方案

### 5.1 单元测试

#### 5.1.1 Handler测试

```python
def test_audit_handler():
    """测试审核Handler"""
    
    handler = AuditHandler()
    
    # 测试1：审核功能开启
    config['agent_audit_enabled'] = 'true'
    
    request = {
        "action": "audit",
        "agent_name": "TestAgent",
        "organization": "TestOrg"
    }
    
    result = handler.handle(request)
    assert result['success'] == True
    assert result['data']['status'] == 'published'
    
    # 测试2：审核功能关闭
    config['agent_audit_enabled'] = 'false'
    
    result = handler.handle(request)
    assert result['success'] == False
    assert result['error'] == "Audit function is disabled"
```

#### 5.1.2 UDS服务测试

```python
def test_uds_service():
    """测试UDS服务"""
    
    # 启动UDS服务（后台线程）
    service = RegistryCenterService()
    thread = threading.Thread(target=service.start, daemon=True)
    thread.start()
    
    # 创建客户端
    client = RegistryClient()
    
    # 测试审核请求
    result = client.audit_agent("TestAgent", "TestOrg")
    assert result['success'] == True
```

### 5.2 集成测试

#### 5.2.1 完整流程测试

```bash
# 测试场景：审核功能开启

# 步骤1：配置审核功能开启
python -m agent_registry.init
# 输入：y

# 步骤2：启动服务
python -m agent_registry.start

# 步骤3：注册Agent（HTTP接口）
curl -X POST http://localhost:9301/rest/a2a-t/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"name":"TestAgent", ...}'

# 预期响应：
{"success":true, "status":"registered", "message":"Agent registered, waiting for audit"}

# 步骤4：审核Agent（UDS接口）
python -m agent_registry.internal.client.cli_registry audit TestAgent TestOrg

# 预期响应：
{"success":true, "message":"Agent audit successful", "data":{"status":"published"}}
```

### 5.3 安全测试

#### 5.3.1 UDS权限测试

```bash
# 测试1：普通用户无法访问
python -m agent_registry.internal.client.cli_registry audit TestAgent TestOrg

# 预期：
Permission denied: You don't have permission

# 测试2：registry_group组成员可以访问
sudo usermod -aG registry_group $USER
python -m agent_registry.internal.client.cli_registry audit TestAgent TestOrg

# 预期：成功
{"success":true, ...}
```

## 6. 运维方案

### 6.1 服务管理

#### 6.1.1 启动服务

```bash
# 方式1：直接启动
python -m agent_registry.start

# 方式2：systemd服务（生产环境推荐）
systemctl start registry-center
```

**systemd配置：**

```ini
# /etc/systemd/system/registry-center.service
[Unit]
Description=Registry Center Service (HTTP + UDS)
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/path/to/registry-center
ExecStart=/usr/bin/python3 -m agent_registry.start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 6.1.2 停止服务

```bash
# 方式1：Ctrl+C

# 方式2：kill进程
kill <PID>

# 方式3：systemd
systemctl stop registry-center
```

#### 6.1.3 状态查看

```bash
# 查看进程
ps aux | grep registry

# 查看socket文件
ls -la /var/run/registry_center.sock

# systemd状态
systemctl status registry-center
```

### 6.2 配置管理

#### 6.2.1 查看配置

```bash
# 查看审核开关
cat etc/conf/server.conf | grep agent_audit_enabled

# 查看UDS配置
cat etc/conf/server.conf | grep uds

# 输出：
uds_service_enabled=true
uds_socket_path=/var/run/registry_center.sock
uds_socket_permissions=660
uds_socket_gid=1000
```

#### 6.2.2 修改配置

```bash
# 通过init命令修改（推荐）
python -m agent_registry.init

# 注意：不能直接修改配置文件关闭审核功能
# 必须通过init命令检查配置一致性
```

### 6.3 Agent状态管理

#### 6.3.1 查询状态

```bash
# 查询所有"已注册"Agent
curl http://localhost:9301/rest/a2a-t/v1/agents/query?status=registered

# 查询所有"已发布"Agent
curl http://localhost:9301/rest/a2a-t/v1/agents/query?status=published
```

#### 6.3.2 批量审核

```python
# 批量审核脚本
from agent_registry.internal.client.registry_client import RegistryClient
from agent_registry.registry_instance import get_registry

client = RegistryClient()
registry = get_registry()

# 获取所有"已注册"Agent
registered_agents = registry.get_agents_by_status('registered')

# 批量审核
for agent in registered_agents:
    result = client.audit_agent(agent.name, agent.provider.organization)
    print(f"{agent.name}: {result['message']}")
```

### 6.4 监控和日志

#### 6.4.1 日志记录

```python
# 审核操作日志
await audit_handle.handle({
    "operation_name": OperationName.AUDIT_AGENT,
    "level": LogLevel.MINOR,
    "result": OperationResult.SUCCESS,
    "object_name": OperatorObject.AGENT,
    "details": {
        "agent_name": "TestAgent",
        "organization": "TestOrg",
        "status": "registered -> published"
    },
    "user_name": "admin"
})
```

#### 6.4.2 统计信息

```python
# Agent状态统计
{
  "total": 100,
  "registered": 20,
  "published": 80
}
```

## 7. 总结

### 7.1 设计要点

#### 7.1.1 进程架构

- **单一进程**：UDS服务和HTTP服务在同一进程
- **多线程**：UDS作为守护线程运行
- **共享资源**：共享RegistryCore实例和配置文件

#### 7.1.2 UDS服务

- **统一入口**：单一socket文件 `/var/run/registry_center.sock`
- **Handler模式**：每个操作独立的Handler类
- **易于扩展**：添加新操作只需新增Handler

#### 7.1.3 配置管理

- **统一配置**：所有配置在`etc/conf/server.conf`
- **单向开关**：审核开关开启后不能关闭
- **UDS无端口**：socket文件路径相当于"端口"

#### 7.1.4 状态管理

- **状态字段**：`status: registered/published`
- **状态转换**：审核开关决定初始状态
- **兼容处理**：旧数据默认为published

### 7.2 核心优势

1. **架构简洁**
   - 单一进程，管理简单
   - 共享数据，无需同步
   - 统一配置，易于维护

2. **易于扩展**
   - Handler模式，易于添加新功能
   - 统一socket，无需创建新服务
   - 客户端统一，易于使用

3. **性能高效**
   - 共享内存，无需IPC
   - 单监听线程，资源占用少
   - UDS本地通信，延迟低

4. **安全可靠**
   - 文件权限控制访问
   - 审核开关防误操作
   - 配置一致性检查

### 7.3 与其他系统对比

| 系统 | Socket文件 | 进程架构 | 扩展机制 |
|------|-----------|---------|---------|
| Docker | `/var/run/docker.sock` | 单进程 | API路由 |
| MySQL | `/var/run/mysql.sock` | 单进程 | SQL解析 |
| PostgreSQL | `/var/run/postgresql.sock` | 单进程 | SQL解析 |
| Registry Center | `/var/run/registry_center.sock` | 单进程 | Handler模式 |

### 7.4 后续扩展方向

1. **更多内部交互操作**
   - 配置管理
   - 统计查询
   - 批量操作
   - 状态重置

2. **权限细化**
   - 不同操作的权限验证
   - 操作审计日志
   - 权限组管理

3. **性能优化**
   - 连接池管理
   - 批量操作支持
   - 异步处理

该设计文档详细说明了注册中心内部交互服务的实现方案，采用统一socket + 同一进程 + Handler模式，为后续实现和扩展提供了完整的设计蓝图。