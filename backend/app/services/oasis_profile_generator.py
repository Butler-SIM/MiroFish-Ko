"""
OASIS Agent Profile생성
Zep그래프진행 중티OASIS시뮬레이션플랫폼Agent Profile

:
1. 호출Zep노드정보
2. 생성상세
3. 엔터티엔터티
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_provider import create_openai_compatible_client
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile"""
    # 
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # 선택 - Reddit
    karma: int = 1000
    
    # 선택 - Twitter
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # 정보
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # 출처엔터티정보
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """Reddit플랫폼"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS  username()
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # 정보()
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """Twitter플랫폼"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS  username()
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # 정보
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile생성
    
    Zep그래프진행 중티OASIS시뮬레이션Agent Profile
    
    :
    1. 호출Zep그래프
    2. 생성상세(정보, , , )
    3. 엔터티엔터티
    """
    
    # MBTI타입목록
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # 목록
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    #개타입엔터티(생성)
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # /타입엔터티(생성)
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY or (
            "codex-cli" if Config.LLM_PROVIDER == "codex_cli" else None
        )
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 설정")
        
        self.client = create_openai_compatible_client(
            model_name=self.model_name,
            api_key=api_key,
            base_url=base_url,
        )
        
        # Zep
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id
        
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Zep실패: {e}")
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        Zep엔터티생성OASIS Agent Profile
        
        Args:
            entity: Zep엔터티노드
            user_id: ID(OASIS)
            use_llm: LLM생성상세
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # 정보
        name = entity.name
        user_name = self._generate_username(name)
        
        # 정보
        context = self._build_entity_context(entity)
        
        if use_llm:
            # LLM생성상세
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # 생성
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """생성"""
        # , 
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # 
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        Zep그래프검색엔터티정보
        
        Zep검색API, 검색edgesnodes.
        병렬요청검색, .
        
        Args:
            entity: 엔터티노드
            
        Returns:
            facts, node_summaries, context
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # graph_id검색
        if not self.graph_id:
            logger.debug(f"Zep:graph_id")
            return results
        
        comprehensive_query = f"{entity_name}정보, , , 관계"
        
        def search_edges():
            """검색엣지(사실/관계)- """
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep엣지검색 {attempt + 1}회실패: {str(e)[:80]}, 진행 중")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep엣지검색 {max_retries}회실패: {e}")
            return None
        
        def search_nodes():
            """검색노드(엔터티요약)- """
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep노드검색 {attempt + 1}회실패: {str(e)[:80]}, 진행 중")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep노드검색 {max_retries}회실패: {e}")
            return None
        
        try:
            # 병렬edgesnodes검색
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # 
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # 엣지검색
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # 노드검색
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"엔터티: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # 
            context_parts = []
            if results["facts"]:
                context_parts.append("사실정보:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("엔터티:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Zep완료: {entity_name},  {len(results['facts'])}건사실, {len(results['node_summaries'])}개노드")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Zep ({entity_name})")
        except Exception as e:
            logger.warning(f"Zep실패 ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        엔터티정보
        
        :
        1. 엔터티엣지정보(사실)
        2. 노드상세정보
        3. Zep정보
        """
        context_parts = []
        
        # 1. 엔터티정보
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### 엔터티\n" + "\n".join(attrs))
        
        # 2. 엣지정보(사실/관계)
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # 
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (엔터티)")
                    else:
                        relationships.append(f"- (엔터티) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### 사실관계\n" + "\n".join(relationships))
        
        # 3. 노드상세정보
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # 
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # 
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### 엔터티정보\n" + "\n".join(related_info))
        
        # 4. Zep정보
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # :사실
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Zep사실정보\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### Zep노드\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """타입엔터티"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """/타입엔터티"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        LLM생성상세
        
        엔터티타입:
        -개엔터티:생성
        - /엔터티:생성
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )

        # 생성, 
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # 
                    # max_tokens, LLM
                )
                
                content = response.choices[0].message.content
                
                # (finish_reason'stop')
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLM (attempt {attempt+1}), ...")
                    content = self._fix_truncated_json(content)
                
                # JSON
                try:
                    result = json.loads(content)
                    
                    # 
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name}{entity_type}."
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON실패 (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLM호출실패 (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # 
        
        logger.warning(f"LLM생성 실패({max_attempts}): {last_error}, 생성")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """JSON(max_tokens)"""
        import re
        
        # JSON, 
        content = content.strip()
        
        # 
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # 
        # :, 
        if content and content[-1] not in '",}]':
            # 
            content += '"'
        
        # 
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """JSON"""
        import re
        
        # 1. 
        content = self._fix_truncated_json(content)
        
        # 2. JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. 진행 중질문
            # 진행 중
            def fix_string_newlines(match):
                s = match.group(0)
                # 
                s = s.replace('\n', ' ').replace('\r', ' ')
                # 
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # JSON
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. 
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. 실패, 
                try:
                    # 
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # 
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. 상세 정보
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # 
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name}{entity_type}.")
        
        # , 
        if bio_match or persona_match:
            logger.info(f"JSON상세 정보")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. 실패, 반환
        logger.warning(f"JSON실패, 반환")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name}{entity_type}."
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """프로필 생성을 위한 시스템 프롬프트를 반환한다."""
        if is_individual:
            return (
                "너는 소셜 시뮬레이션용 인물 프로필 생성기다. "
                "항상 유효한 JSON만 반환하고, 지정된 필드를 빠짐없이 채워라."
            )
        return (
            "너는 소셜 시뮬레이션용 기관/집단 계정 프로필 생성기다. "
            "항상 유효한 JSON만 반환하고, 지정된 필드를 빠짐없이 채워라."
        )
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """개인 엔터티용 프롬프트를 구성한다."""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else ""
        context_str = context[:3000] if context else ""
        
        return f"""다음 개인 엔터티 정보를 바탕으로 프로필 JSON을 생성해 주세요.

엔터티 이름: {entity_name}
엔터티 타입: {entity_type}
엔터티 요약: {entity_summary}
엔터티 속성: {attrs_str}

참고 컨텍스트:
{context_str}

반드시 아래 키를 포함한 JSON만 반환하세요:
1. bio: 200자 이내의 간단한 소개
2. persona: 2000자 이내의 상세 성격/행동 특성
3. age: 정수
4. gender: "male" 또는 "female"
5. mbti: MBTI 문자열(예: INTJ, ENFP)
6. country: 국가명 문자열
7. profession: 직업/역할
8. interested_topics: 관심 주제 문자열 배열

제약:
- JSON 외 텍스트 금지
- persona는 구체적이고 일관되게 작성
- age/gender 형식 반드시 준수
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """기관/집단 엔터티용 프롬프트를 구성한다."""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else ""
        context_str = context[:3000] if context else ""
        
        return f"""다음 기관/집단 엔터티 정보를 바탕으로 프로필 JSON을 생성해 주세요.

엔터티 이름: {entity_name}
엔터티 타입: {entity_type}
엔터티 요약: {entity_summary}
엔터티 속성: {attrs_str}

참고 컨텍스트:
{context_str}

반드시 아래 키를 포함한 JSON만 반환하세요:
1. bio: 200자 이내 소개
2. persona: 2000자 이내 상세 설명
3. age: 30 (고정)
4. gender: "other" (고정)
5. mbti: "ISTJ" (기본값)
6. country: 국가명 문자열
7. profession: 기관 역할/직종
8. interested_topics: 관심 주제 문자열 배열

제약:
- JSON 외 텍스트 금지
- 기관 계정 톤으로 작성
- age=30, gender=\"other\" 유지
"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """생성"""
        
        # 엔터티타입생성
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_attributes.get("occupation", "Expert"),
                "interested_topics": ["Politics", "Economics", "Culture & Society"],
            }
        
        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "bio": f"Official account for {entity_name}. News and updates.",
                "persona": f"{entity_name} is a media entity that reports news and facilitates public discourse. The account shares timely updates and engages with the audience on current events.",
                "age": 30,
                "gender": "other",
                "mbti": "ISTJ",
                "country": "South Korea",
                "profession": "Media",
                "interested_topics": ["General News", "Current Events", "Public Affairs"],
            }
        
        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "bio": f"Official account of {entity_name}.",
                "persona": f"{entity_name} is an institutional entity that communicates official positions, announcements, and engages with stakeholders on relevant matters.",
                "age": 30,
                "gender": "other",
                "mbti": "ISTJ",
                "country": "South Korea",
                "profession": entity_type,
                "interested_topics": ["Public Policy", "Community", "Official Announcements"],
            }
        
        else:
            # 
            return {
                "bio": entity_summary[:150] if entity_summary else f"{entity_type}: {entity_name}",
                "persona": entity_summary or f"{entity_name} is a {entity_type.lower()} participating in social discussions.",
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["General", "Social Issues"],
            }
    
    def set_graph_id(self, graph_id: str):
        """그래프IDZep"""
        self.graph_id = graph_id
    
    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        엔터티생성Agent Profile(병렬생성)
        
        Args:
            entities: 엔터티목록
            use_llm: LLM생성상세
            progress_callback: 진행률 (current, total, message)
            graph_id: 그래프ID, Zep
            parallel_count: 병렬생성, 5
            realtime_output_path: 쓰기파일(, 생성쓰기)
            output_platform: 플랫폼 ("reddit"  "twitter")
            
        Returns:
            Agent Profile목록
        """
        import concurrent.futures
        from threading import Lock
        
        # graph_idZep
        if graph_id:
            self.graph_id = graph_id
        
        total = len(entities)
        profiles = [None] * total  # 목록
        completed_count = [0]  # 목록
        lock = Lock()
        
        # 쓰기파일
        def save_profiles_realtime():
            """저장생성 profiles 파일"""
            if not realtime_output_path:
                return
            
            with lock:
                # 생성 profiles
                existing_profiles = [p for p in profiles if p is not None]
                if not existing_profiles:
                    return
                
                try:
                    if output_platform == "reddit":
                        # Reddit JSON 
                        profiles_data = [p.to_reddit_format() for p in existing_profiles]
                        with open(realtime_output_path, 'w', encoding='utf-8') as f:
                            json.dump(profiles_data, f, ensure_ascii=False, indent=2)
                    else:
                        # Twitter CSV 
                        import csv
                        profiles_data = [p.to_twitter_format() for p in existing_profiles]
                        if profiles_data:
                            fieldnames = list(profiles_data[0].keys())
                            with open(realtime_output_path, 'w', encoding='utf-8', newline='') as f:
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(profiles_data)
                except Exception as e:
                    logger.warning(f"저장 profiles 실패: {e}")
        
        def generate_single_profile(idx: int, entity: EntityNode) -> tuple:
            """생성profile"""
            entity_type = entity.get_entity_type() or "Entity"
            
            try:
                profile = self.generate_profile_from_entity(
                    entity=entity,
                    user_id=idx,
                    use_llm=use_llm
                )
                
                # 생성콘솔로그
                self._print_generated_profile(entity.name, entity_type, profile)
                
                return idx, profile, None
                
            except Exception as e:
                logger.error(f"생성엔터티 {entity.name} 실패: {str(e)}")
                # profile
                fallback_profile = OasisAgentProfile(
                    user_id=idx,
                    user_name=self._generate_username(entity.name),
                    name=entity.name,
                    bio=f"{entity_type}: {entity.name}",
                    persona=entity.summary or f"A participant in social discussions.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback_profile, str(e)
        
        logger.info(f"시작병렬생성 {total}개Agent(병렬: {parallel_count})...")
        print(f"\n{'='*60}")
        print(f"시작생성Agent - 총 {total}개엔터티, 병렬: {parallel_count}")
        print(f"{'='*60}\n")
        
        # 병렬
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # 작업
            future_to_entity = {
                executor.submit(generate_single_profile, idx, entity): (idx, entity)
                for idx, entity in enumerate(entities)
            }
            
            # 
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                entity_type = entity.get_entity_type() or "Entity"
                
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    
                    # 쓰기파일
                    save_profiles_realtime()
                    
                    if progress_callback:
                        progress_callback(
                            current, 
                            total, 
                            f"완료 {current}/{total}: {entity.name}({entity_type})"
                        )
                    
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} : {error}")
                    else:
                        logger.info(f"[{current}/{total}] 생성: {entity.name} ({entity_type})")
                        
                except Exception as e:
                    logger.error(f"엔터티 {entity.name} : {str(e)}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = OasisAgentProfile(
                        user_id=idx,
                        user_name=self._generate_username(entity.name),
                        name=entity.name,
                        bio=f"{entity_type}: {entity.name}",
                        persona=entity.summary or "A participant in social discussions.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    # 쓰기파일()
                    save_profiles_realtime()
        
        print(f"\n{'='*60}")
        print(f"생성완료!생성 {len([p for p in profiles if p])}개Agent")
        print(f"{'='*60}\n")
        
        return profiles
    
    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: OasisAgentProfile):
        """생성콘솔(, )"""
        separator = "-" * 70
        
        # ()
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else ''
        
        output_lines = [
            f"\n{separator}",
            f"[생성] {entity_name} ({entity_type})",
            f"{separator}",
            f": {profile.user_name}",
            f"",
            f"[]",
            f"{profile.bio}",
            f"",
            f"[상세]",
            f"{profile.persona}",
            f"",
            f"[]",
            f": {profile.age} | : {profile.gender} | MBTI: {profile.mbti}",
            f": {profile.profession} | : {profile.country}",
            f": {topics_str}",
            separator
        ]
        
        output = "\n".join(output_lines)
        
        # 콘솔(, logger)
        print(output)
    
    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        저장Profile파일(플랫폼선정)
        
        OASIS플랫폼:
        - Twitter: CSV
        - Reddit: JSON
        
        Args:
            profiles: Profile목록
            file_path: 파일
            platform: 플랫폼타입 ("reddit"  "twitter")
        """
        if platform == "twitter":
            self._save_twitter_csv(profiles, file_path)
        else:
            self._save_reddit_json(profiles, file_path)
    
    def _save_twitter_csv(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        OASIS Twitter 프로필을 CSV 형식으로 저장한다.

        컬럼 설명:
        - user_id: CSV 기준 순번(0부터 시작)
        - name: 표시 이름
        - username: 계정명
        - user_char: 상세 캐릭터 설명(LLM 생성)
        - description: 짧은 소개 문구

        참고:
        - user_char는 `bio + persona`를 결합한 확장 설명
        - description은 짧고 읽기 쉬운 요약 텍스트
        """
        import csv
        
        # 파일.csv
        if not file_path.endswith('.csv'):
            file_path = file_path.replace('.json', '.csv')
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 쓰기OASIS
            headers = ['user_id', 'name', 'username', 'user_char', 'description']
            writer.writerow(headers)
            
            # 쓰기
            for idx, profile in enumerate(profiles):
                # user_char: (bio + persona), LLM
                user_char = profile.bio
                if profile.persona and profile.persona != profile.bio:
                    user_char = f"{profile.bio} {profile.persona}"
                # CSV 저장을 위해 개행 문자를 공백으로 정리
                user_char = user_char.replace('\n', ' ').replace('\r', ' ')
                
                # description: , 
                description = profile.bio.replace('\n', ' ').replace('\r', ' ')
                
                row = [
                    idx,                    # user_id: 0시작ID
                    profile.name,           # name: 
                    profile.user_name,      # username: 
                    user_char,              # user_char: (LLM)
                    description             # description: ()
                ]
                writer.writerow(row)
        
        logger.info(f"저장 {len(profiles)}개Twitter Profile {file_path} (OASIS CSV)")
    
    def _normalize_gender(self, gender: Optional[str]) -> str:
        """
        genderOASIS
        
        OASIS: male, female, other
        """
        if not gender:
            return "other"
        
        gender_lower = gender.lower().strip()
        
        # 진행 중
        gender_map = {
            "": "male",
            "": "female",
            "": "other",
            "": "other",
            # 
            "male": "male",
            "female": "female",
            "other": "other",
        }
        
        return gender_map.get(gender_lower, "other")
    
    def _save_reddit_json(self, profiles: List[OasisAgentProfile], file_path: str):
        """
        저장Reddit ProfileJSON
        
         to_reddit_format() ,  OASIS 읽기.
         user_id ,  OASIS agent_graph.get_agent() 핵심!
        
        :
        - user_id: ID(,  initial_posts poster_agent_id)
        - username: 
        - name: 
        - bio: 
        - persona: 상세
        - age: ()
        - gender: "male", "female",  "other"
        - mbti: MBTI타입
        - country: 
        """
        data = []
        for idx, profile in enumerate(profiles):
            #  to_reddit_format() 
            item = {
                "user_id": profile.user_id if profile.user_id is not None else idx,  # 핵심: user_id
                "username": profile.user_name,
                "name": profile.name,
                "bio": profile.bio[:150] if profile.bio else f"{profile.name}",
                "persona": profile.persona or f"{profile.name} is a participant in social discussions.",
                "karma": profile.karma if profile.karma else 1000,
                "created_at": profile.created_at,
                # OASIS - 
                "age": profile.age if profile.age else 30,
                "gender": self._normalize_gender(profile.gender),
                "mbti": profile.mbti if profile.mbti else "ISTJ",
                "country": profile.country if profile.country else "South Korea",
            }
            
            # 선택
            if profile.profession:
                item["profession"] = profile.profession
            if profile.interested_topics:
                item["interested_topics"] = profile.interested_topics
            
            data.append(item)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"저장 {len(profiles)}개Reddit Profile {file_path} (JSON, user_id)")
    
    # , 
    def save_profiles_to_json(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """[]  save_profiles() """
        logger.warning("save_profiles_to_json, save_profiles")
        self.save_profiles(profiles, file_path, platform)
