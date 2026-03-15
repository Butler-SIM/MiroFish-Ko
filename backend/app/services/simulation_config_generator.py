"""
시뮬레이션 실행에 필요한 설정 파라미터를 생성한다.

입력:
- 시뮬레이션 요구사항
- 그래프 엔터티 정보
- LLM 분석 결과

출력:
1. 시간/라운드 설정
2. 이벤트 설정
3. 에이전트 활동 설정
4. 플랫폼별 설정
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_provider import create_openai_compatible_client
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.simulation_config')

# 시간대 기본 설정(한국/동아시아 소셜 활동 패턴 기준)
CHINA_TIMEZONE_CONFIG = {
    # 심야
    "dead_hours": [0, 1, 2, 3, 4, 5],
    # 아침
    "morning_hours": [6, 7, 8],
    # 업무 시간
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # 저녁 피크
    "peak_hours": [19, 20, 21, 22],
    # 늦은 밤
    "night_hours": [23],
    # 시간대별 활동 가중치
    "activity_multipliers": {
        "dead": 0.05,
        "morning": 0.4,
        "work": 0.7,
        "peak": 1.5,
        "night": 0.5
    }
}


@dataclass
class AgentActivityConfig:
    """에이전트 활동 설정"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str
    
    # 전반적 활동성(0.0-1.0)
    activity_level: float = 0.5
    
    # 시간당 생성량
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0
    
    # 활동 시간대(24시간 기준)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))
    
    # 반응 지연(분)
    response_delay_min: int = 5
    response_delay_max: int = 60
    
    # 감성 편향(-1.0~1.0)
    sentiment_bias: float = 0.0
    
    # 입장
    stance: str = "neutral"  # supportive, opposing, neutral, observer
    
    # 영향력 가중치
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """시뮬레이션 시간/활동 설정"""
    # 전체 시뮬레이션 시간(기본 72시간)
    total_simulation_hours: int = 72
    
    # 라운드당 분 단위(기본 60분)
    minutes_per_round: int = 60
    
    # 시간당 활성 에이전트 수 범위
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20
    
    # 저녁 피크
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5
    
    # 심야 비활성 시간
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05
    
    # 아침
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4
    
    # 업무 시간
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class EventConfig:
    """시뮬레이션 이벤트 설정"""
    # 시뮬레이션 시작 시점의 초기 게시물
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)
    
    # 예약 이벤트
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)
    
    # 핵심 이슈
    hot_topics: List[str] = field(default_factory=list)
    
    # 
    narrative_direction: str = ""


@dataclass
class PlatformConfig:
    """플랫폼 설정"""
    platform: str  # twitter or reddit
    
    # 랭킹 가중치
    recency_weight: float = 0.4
    popularity_weight: float = 0.3
    relevance_weight: float = 0.3
    
    # 바이럴 임계치
    viral_threshold: int = 10
    
    # 에코챔버 강도
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """시뮬레이션 전체 파라미터 묶음"""
    # 기본 정보
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    
    # 시간 설정
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)
    
    # 에이전트 설정 목록
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)
    
    # 이벤트 설정
    event_config: EventConfig = field(default_factory=EventConfig)
    
    # 플랫폼 설정
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None
    
    # LLM 설정
    llm_model: str = ""
    llm_base_url: str = ""
    
    # 생성 정보
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    시뮬레이션 요구사항과 그래프 정보를 바탕으로
    실행 가능한 설정 파라미터를 생성한다.

    생성 항목:
    1. 시간/라운드 설정
    2. 에이전트 활동 설정
    3. 이벤트 설정
    4. 플랫폼 설정
    """
    
    # 
    MAX_CONTEXT_LENGTH = 50000
    # 생성Agent
    AGENTS_PER_BATCH = 15
    
    # ()
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # 설정
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # 설정
    ENTITY_SUMMARY_LENGTH = 300          # 엔터티요약
    AGENT_SUMMARY_LENGTH = 300           # Agent설정진행 중티요약
    ENTITIES_PER_TYPE_DISPLAY = 20       # 엔터티
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
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
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        생성시뮬레이션설정(생성)
        
        Args:
            simulation_id: 시뮬레이션ID
            project_id: 프로젝트ID
            graph_id: 그래프ID
            simulation_requirement: 시뮬레이션
            document_text: 
            entities: 엔터티목록
            enable_twitter: Twitter
            enable_reddit: Reddit
            progress_callback: 진행률(current_step, total_steps, message)
            
        Returns:
            SimulationParameters: 시뮬레이션 파라미터
        """
        logger.info(f"시작생성시뮬레이션설정: simulation_id={simulation_id}, 엔터티={len(entities)}")
        
        # 
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # 설정 + 설정 + NAgent + 플랫폼설정
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. 정보
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )
        
        reasoning_parts = []
        
        # ========== 1: 생성설정 ==========
        report_progress(1, "생성설정...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"설정: {time_config_result.get('reasoning', '')}")
        
        # ========== 2: 생성설정 ==========
        report_progress(2, "생성설정...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        event_config = self._parse_event_config(event_config_result)
        reasoning_parts.append(f"설정: {event_config_result.get('reasoning', '')}")
        
        # ========== 3-N: 생성Agent설정 ==========
        all_agent_configs = []
        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.AGENTS_PER_BATCH
            end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
            batch_entities = entities[start_idx:end_idx]
            
            report_progress(
                3 + batch_idx,
                f"생성Agent설정 ({start_idx + 1}-{end_idx}/{len(entities)})..."
            )
            
            batch_configs = self._generate_agent_configs_batch(
                context=context,
                entities=batch_entities,
                start_idx=start_idx,
                simulation_requirement=simulation_requirement
            )
            all_agent_configs.extend(batch_configs)
        
        reasoning_parts.append(f"Agent설정: 생성 {len(all_agent_configs)}개")
        
        # ==========  Agent ==========
        logger.info(" Agent...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f": {assigned_count}개")
        
        # ========== : 생성플랫폼설정 ==========
        report_progress(total_steps, "생성플랫폼설정...")
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # 파라미터
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(f"시뮬레이션설정생성완료: {len(params.agent_configs)}개Agent설정")
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """LLM, """
        
        # 엔터티요약
        entity_summary = self._summarize_entities(entities)
        
        # 
        context_parts = [
            f"## 시뮬레이션\n{simulation_requirement}",
            f"\n## 엔터티정보 ({len(entities)})\n{entity_summary}",
        ]
        
        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # 500
        
        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...()"
            context_parts.append(f"\n## \n{doc_text}")
        
        return "\n".join(context_parts)
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """생성엔터티요약"""
        lines = []
        
        # 타입
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)})")
            # 설정요약
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ...  {len(type_entities) - display_count}개")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """LLM호출, JSON"""
        import re
        
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # 
                    # max_tokens, LLM
                )
                
                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason
                
                # 
                if finish_reason == 'length':
                    logger.warning(f"LLM (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)
                
                # JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON실패 (attempt {attempt+1}): {str(e)[:80]}")
                    
                    # JSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(f"LLM호출실패 (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("LLM호출실패")
    
    def _fix_truncated_json(self, content: str) -> str:
        """JSON"""
        content = content.strip()
        
        # 
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # 
        if content and content[-1] not in '",}]':
            content += '"'
        
        # 
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """설정JSON"""
        import re
        
        # 
        content = self._fix_truncated_json(content)
        
        # JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 진행 중
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # 
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """시간/활동 설정을 생성한다."""
        # 컨텍스트 길이 제한
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
        
        # 시간당 최대 활성 에이전트 상한(전체의 90%)
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""다음 정보를 바탕으로 시뮬레이션 시간 설정 JSON을 생성하세요.

{context_truncated}

## 작업
시간대별 활동 패턴을 반영한 `time_config`를 작성하세요.

## 시간대 가이드
- 0~5시: 활동 매우 낮음(기본 0.05)
- 6~8시: 활동 낮음(기본 0.4)
- 9~18시: 활동 보통(기본 0.7)
- 19~22시: 활동 높음(기본 1.5)
- 23시: 활동 중간(기본 0.5)
- `peak_hours`와 `off_peak_hours`는 겹치지 않게 구성

## 출력 규칙
- 마크다운 코드블록 없이 JSON 객체만 반환
- 값 범위:
  - total_simulation_hours: 24~168
  - minutes_per_round: 30~120
  - agents_per_hour_min/max: 1~{max_agents_allowed}

{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "설정 근거"
}}

- reasoning에는 설정 이유를 한국어 한 문장으로 작성하세요."""

        system_prompt = "당신은 시뮬레이션 시간 설정 전문가입니다. JSON 객체만 반환하세요."
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"시간 설정 생성 실패: {e}. 기본 설정으로 대체합니다.")
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """시간 설정 기본값을 반환한다."""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 1라운드 = 60분
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "기본 시간대 가중치 설정"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """LLM 결과를 TimeSimulationConfig로 정규화한다."""
        # 기본값
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))
        
        # 에이전트 수 상한 보정
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min({agents_per_hour_min})가 엔터티 수({num_entities})를 초과해 보정합니다.")
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max({agents_per_hour_max})가 엔터티 수({num_entities})를 초과해 보정합니다.")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        #  min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min이 max 이상이라 보정했습니다: {agents_per_hour_min}")
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # 1
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """이벤트 설정을 생성한다."""
        
        # 엔터티 타입 목록
        entity_types_available = list(set(
            e.get_entity_type() or "Unknown" for e in entities
        ))
        
        # 타입별 예시 엔터티
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # 컨텍스트 길이 제한
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        
        prompt = f"""다음 정보를 바탕으로 이벤트 설정 JSON을 생성하세요.

시뮬레이션: {simulation_requirement}

{context_truncated}

## 엔터티타입
{type_info}

## 작업
아래 항목을 포함한 `event_config`를 작성하세요.
- hot_topics: 시뮬레이션 핵심 이슈 3~7개
- narrative_direction: 담론 흐름 한 줄 요약
- initial_posts: 시작 시점 게시물 3~10개
- 각 initial_post는 `content`, `poster_type` 필수

`poster_type`은 아래 엔터티 타입 중 하나를 사용:
- Official / University / MediaOutlet / Student / Person / Alumni / Organization

출력 규칙:
- 마크다운 없이 JSON 객체만 반환

{{
    "hot_topics": ["핵심1", "핵심2", ...],
    "narrative_direction": "담론 방향 요약",
    "initial_posts": [
        {{"content": "초기 게시물 내용", "poster_type": "Student"}},
        ...
    ],
    "reasoning": "설정 근거"
}}"""

        system_prompt = "당신은 시뮬레이션 이벤트 설계 전문가입니다. JSON만 반환하세요."
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"이벤트 설정 생성 실패: {e}. 빈 기본값으로 대체합니다.")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "기본 이벤트 설정"
            }
    
    def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
        """LLM 결과를 EventConfig로 변환한다."""
        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=[],
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", "")
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        초기 게시물의 `poster_type`을 기준으로 에이전트를 매핑한다.
        """
        if not event_config.initial_posts:
            return event_config
        
        # 엔터티 타입별 에이전트 분류
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)
        
        # LLM이 사용할 수 있는 타입 별칭
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
        }
        
        # 타입별 순환 배정 인덱스
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # 매칭 대상 에이전트 ID
            matched_agent_id = None
            
            # 1) 정확히 일치하는 타입 우선
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2) 별칭 기반으로 보조 매칭
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3) 그래도 없으면 영향력 높은 에이전트로 대체
            if matched_agent_id is None:
                logger.warning(f"poster_type '{poster_type}'에 맞는 에이전트가 없어 대체 매핑합니다.")
                if agent_configs:
                    # 영향력 높은 에이전트 우선
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(f"초기 게시물 매핑: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
        
        event_config.initial_posts = updated_posts
        return event_config
    
    def _generate_agent_configs_batch(
        self,
        context: str,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """배치 단위로 에이전트 활동 설정을 생성한다."""
        
        # 엔터티 입력 요약
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""아래 엔터티 목록을 보고 에이전트 활동 설정 JSON을 생성하세요.

시뮬레이션: {simulation_requirement}

## 엔터티목록
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## 작업
각 엔터티에 대해 다음 필드를 채우세요:
- activity_level(0.0~1.0)
- posts_per_hour, comments_per_hour
- active_hours(정수 배열, 0~23)
- response_delay_min/max(분)
- sentiment_bias(-1.0~1.0)
- stance(supportive/opposing/neutral/observer)
- influence_weight(0.1 이상)

권장 가이드:
- University/GovernmentAgency: 활동 낮음, 응답 느림, 영향력 높음
- MediaOutlet: 활동 높음, 응답 빠름, 영향력 중상
- Student/Person/Alumni: 활동 중간~높음, 응답 빠름, 영향력 중간

출력 규칙:
- 마크다운 없이 JSON 객체만 반환

{{
    "agent_configs": [
        {{
            "agent_id": <>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <>,
            "comments_per_hour": <>,
            "active_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
            "response_delay_min": <>,
            "response_delay_max": <>,
            "sentiment_bias": <-1.0~1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <>
        }},
        ...
    ]
}}"""

        system_prompt = "당신은 에이전트 행동 시뮬레이션 설계 전문가입니다. JSON만 반환하세요."
        
        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"에이전트 설정 생성 실패: {e}. 규칙 기반 기본값으로 대체합니다.")
            llm_configs = {}
        
        # AgentActivityConfig
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            
            # LLM 결과가 없으면 규칙 기반 기본값 사용
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """엔터티 타입 기반 규칙으로 기본 에이전트 설정을 생성한다."""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        
        if entity_type in ["university", "governmentagency", "ngo"]:
            # 기관/공공 성격: 저빈도, 고영향
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # 미디어: 고빈도, 빠른 반응
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # 전문가/공식 계정: 중간 활동, 상대적으로 높은 영향력
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # :, 
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # +
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # :
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # +
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # :
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # +
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    
