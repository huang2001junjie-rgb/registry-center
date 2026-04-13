import base64
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

from a2a.types import AgentCard
from a2a.utils.signing import create_signature_verifier, InvalidSignaturesError, NoSignatureError

from agent_registry.signature.models import (
    SignatureObject, ProtectedHeader, JWK, JWKS
)
from agent_registry.signature.public_key_manager import PublicKeyManager
from agent_registry.signature.storage import StoragePath


class ValidationResult:
    """验证结果"""
    def __init__(
        self,
        is_valid: bool,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.is_valid = is_valid
        self.error_code = error_code
        self.error_message = error_message
        self.details = details or {}


class AgentCardValidator:
    """AgentCard签名验证器"""
    
    def __init__(self, public_key_manager: PublicKeyManager):
        self.public_key_manager = public_key_manager
    
    def validate_agent_card(
        self,
        agent_card_data: dict,
        organization: str,
        agent_name: str
    ) -> ValidationResult:
        """
        验证AgentCard的签名
        
        Args:
            agent_card_data: AgentCard数据
            organization: 组织名称
            agent_name: Agent名称
        
        Returns:
            ValidationResult: 验证结果
        """
        try:
            # 根据请求信息初始化agent_card变量
            agent_card = AgentCard(**agent_card_data)
            # 步骤1：提取signatures字段
            signatures = self._extract_signatures(agent_card_data)
            if not signatures:
                return ValidationResult(
                    is_valid=False,
                    error_code="SIG001",
                    error_message="Signatures field is required when signature validation is enabled",
                    details={
                        "validation_enabled": True,
                        "signatures_found": False
                    }
                )
            
            # 步骤2：构造payload（不包含signatures）
            agent_card_copy = agent_card_data.copy()
            del agent_card_copy["signatures"]
            payload = json.dumps(agent_card_copy, sort_keys=True)
            
            # 步骤3：遍历signatures数组(多个signature验签的情况下成功一个即视为验证通过)
            for sig_obj in signatures:
                # 解码protected头
                protected_header = self._decode_protected(sig_obj.protected)
                if not protected_header:
                    logger.warning(f"Failed to decode protected header: {sig_obj.protected}")
                    continue
                
                kid = protected_header.kid
                
                # 步骤4：优先从后台获取公钥
                backend_key = self._try_backend_key(kid, organization, agent_name)
                if backend_key:
                    logger.info(f"Using backend key for kid: {kid}")
                    # 使用后台公钥验签
                    if self._verify_with_jose(
                        sig_obj.protected,
                        payload,
                        sig_obj.signature,
                        backend_key
                    ):
                        logger.info(f"Signature validation passed with backend key: {kid}")
                        return ValidationResult(is_valid=True)
                
            # 步骤5：若后台验签失败则通过jku签名链接重试一次，直接调用a2a-sdk的能力
            logger.info(f"Trying jku key signature.")
            a2a_sdk_verifier = create_signature_verifier(self._try_jku_key, ['ES256', 'RS256'])
            try:
                a2a_sdk_verifier(agent_card)
                logger.info(f"Signature validation passed with jku key.")
                return ValidationResult(is_valid=True)
            except NoSignatureError:
                logger.error("No jku key found.")
            except InvalidSignaturesError:
                logger.error("Jku key signature validations failed")
            
            # 所有签名都验证失败
            logger.error("All signature validations failed")
            return ValidationResult(
                is_valid=False,
                error_code="SIG005",
                error_message="All signature validations failed",
                details={
                    "total_signatures": len(signatures)
                }
            )
            
        except Exception as e:
            logger.error(f"AgentCard validation error: {e}")
            return ValidationResult(
                is_valid=False,
                error_code="SIG999",
                error_message="Internal server error",
                details={"error": str(e)}
            )
    
    def _extract_signatures(self, agent_card_data: dict) -> List[SignatureObject]:
        """提取signatures字段"""
        try:
            signatures = agent_card_data.get("signatures")
            if not signatures:
                return []
            
            signature_objects = []
            for sig in signatures:
                if not isinstance(sig, dict):
                    logger.warning(f"Invalid signature format: {sig}")
                    continue
                
                if "protected" not in sig or "signature" not in sig:
                    logger.warning("Missing required fields in signature")
                    continue
                
                signature_objects.append(SignatureObject(**sig))
            
            return signature_objects
            
        except Exception as e:
            logger.error(f"Failed to extract signatures: {e}")
            return []
    
    def _decode_protected(self, protected: str) -> Optional[ProtectedHeader]:
        """解码protected头"""
        try:
            # base64url解码
            decoded_bytes = base64.urlsafe_b64decode(protected)
            # 添加填充符
            padding = 4 - len(protected) % 4
            if padding != 4:
                decoded_bytes += b'=' * padding
            
            # 解码JSON
            protected_json = decoded_bytes.decode('utf-8')
            protected_dict = json.loads(protected_json)
            
            return ProtectedHeader(**protected_dict)
            
        except Exception as e:
            logger.error(f"Failed to decode protected header: {e}")
            return None
    
    def _try_backend_key(
        self,
        kid: str,
        organization: str,
        agent_name: str
    ) -> Optional[JWK]:
        """尝试从后台获取公钥"""
        try:
            jwk = self.public_key_manager.get_public_key(organization, agent_name, kid)
            if jwk:
                logger.info(f"Found backend key for kid: {kid}")
                return jwk
            else:
                logger.info(f"Backend key not found for kid: {kid}")
                return None
        except Exception as e:
            logger.error(f"Failed to get backend key: {e}")
            return None
    
    def _try_jku_key(
        self,
        jku: str,
        kid: str
    ) -> Optional[JWK]:
        """尝试从jku获取临时公钥"""
        try:
            from agent_registry.signature.jwk_fetcher import JWKFetcher
            
            fetcher = JWKFetcher()
            jwks = fetcher.fetch_jwks(jku)
            
            if jwks:
                jwk = fetcher.find_key_by_id(jwks, kid)
                if jwk:
                    logger.info(f"Found jku key for kid: {kid}")
                    return jwk
                else:
                    logger.info(f"Jku key not found in JWKS for kid: {kid}")
                    return None
            else:
                logger.warning(f"No keys found in JWKS")
                return None
        except Exception as e:
            logger.error(f"Failed to get jku key: {e}")
            return None
    
    def _verify_with_jose(
        self,
        protected: str,
        payload: str,
        signature: str,
        public_key: JWK
    ) -> bool:
        """
        使用python-jose进行签名验证
        
        Args:
            protected: base64url编码的protected头
            payload: AgentCard的JSON字符串（不包含signatures）
            signature: base64url编码的签名值
            public_key: JWK格式的公钥字典
        
        Returns:
            bool: 验证结果
        """
        try:
            # 构造JWS字符串
            jws_string = f"{protected}.{payload}.{signature}"
            
            # 从JWK构造公钥对象
            public_key_dict = public_key.model_dump()
            
            # 使用python-jose验证签名
            jws.verify(
                jws_string,
                public_key_dict,
                algorithms=['ES256', 'RS256']
            )
            
            logger.debug("JWS signature verification passed")
            return True
            
        except (JWSError, JWKError) as e:
            logger.warning(f"JWS signature verification failed: {e}")
            return False
        except Exception as e:
            logger.error(f"JWS signature verification error: {e}")
            return False