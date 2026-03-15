"""
OASIS Twitter 시뮬레이션 실행 스크립트.

기능:
- 설정 파일을 읽어 Twitter 시뮬레이션 실행
- 시뮬레이션 종료 후 IPC 인터뷰 명령 대기
- 에이전트 단건/배치 인터뷰 처리

사용 예:
    python run_twitter_simulation.py --config /path/to/simulation_config.json
    python run_twitter_simulation.py --config /path/to/simulation_config.json --no-wait
"""

import argparse
import asyncio
import json
import logging
import os
import random
import signal
import sys
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional

# 종료 제어용 전역 플래그
_shutdown_event = None
_cleanup_done = False

# 프로젝트
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, '..'))
_project_root = os.path.abspath(os.path.join(_backend_dir, '..'))
sys.path.insert(0, _scripts_dir)
sys.path.insert(0, _backend_dir)

# 프로젝트 루트의 .env 로드(LLM_API_KEY 등)
from dotenv import load_dotenv
_env_file = os.path.join(_project_root, '.env')
if os.path.exists(_env_file):
    load_dotenv(_env_file)
else:
    _backend_env = os.path.join(_backend_dir, '.env')
    if os.path.exists(_backend_env):
        load_dotenv(_backend_env)


import re


class UnicodeFormatter(logging.Formatter):
    """로그 문자열의 유니코드 이스케이프를 실제 문자로 변환한다."""
    
    UNICODE_ESCAPE_PATTERN = re.compile(r'\\u([0-9a-fA-F]{4})')
    
    def format(self, record):
        result = super().format(record)
        
        def replace_unicode(match):
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return match.group(0)
        
        return self.UNICODE_ESCAPE_PATTERN.sub(replace_unicode, result)


class MaxTokensWarningFilter(logging.Filter):
    """camel-ai의 반복적인 max_tokens 경고 로그를 필터링한다."""
    
    def filter(self, record):
        #  max_tokens 경고로그
        if "max_tokens" in record.getMessage() and "Invalid or missing" in record.getMessage():
            return False
        return True


# camel-ai 경고 필터 등록
logging.getLogger().addFilter(MaxTokensWarningFilter())


def setup_oasis_logging(log_dir: str):
    """OASIS 로그 파일 핸들러를 초기화한다."""
    os.makedirs(log_dir, exist_ok=True)
    
    # 로그파일
    for f in os.listdir(log_dir):
        old_log = os.path.join(log_dir, f)
        if os.path.isfile(old_log) and f.endswith('.log'):
            try:
                os.remove(old_log)
            except OSError:
                pass
    
    formatter = UnicodeFormatter("%(levelname)s - %(asctime)s - %(name)s - %(message)s")
    
    loggers_config = {
        "social.agent": os.path.join(log_dir, "social.agent.log"),
        "social.twitter": os.path.join(log_dir, "social.twitter.log"),
        "social.rec": os.path.join(log_dir, "social.rec.log"),
        "oasis.env": os.path.join(log_dir, "oasis.env.log"),
        "table": os.path.join(log_dir, "table.log"),
    }
    
    for logger_name, log_file in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.propagate = False


try:
    import oasis
    from oasis import (
        ActionType,
        LLMAction,
        ManualAction,
        generate_twitter_agent_graph
    )
    from app.utils.llm_provider import create_camel_model_backend
except ImportError as e:
    print(f"오류: 누락 {e}")
    print(": pip install oasis-ai camel-ai")
    sys.exit(1)


# IPC
IPC_COMMANDS_DIR = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE = "env_status.json"

class CommandType:
    """IPC 명령 타입."""
    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"


class IPCHandler:
    """IPC 인터뷰 명령 처리기."""
    
    def __init__(self, simulation_dir: str, env, agent_graph):
        self.simulation_dir = simulation_dir
        self.env = env
        self.agent_graph = agent_graph
        self.commands_dir = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file = os.path.join(simulation_dir, ENV_STATUS_FILE)
        self._running = True
        
        # 디렉터리
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
    
    def update_status(self, status: str):
        """상태"""
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def poll_command(self) -> Optional[Dict[str, Any]]:
        """명령 디렉터리에서 가장 오래된 명령 파일을 읽는다."""
        if not os.path.exists(self.commands_dir):
            return None
        
        # 파일()
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))
        
        command_files.sort(key=lambda x: x[1])
        
        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
        
        return None
    
    def send_response(self, command_id: str, status: str, result: Dict = None, error: str = None):
        """IPC 응답 파일을 기록하고 처리된 명령 파일을 삭제한다."""
        response = {
            "command_id": command_id,
            "status": status,
            "result": result,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response, f, ensure_ascii=False, indent=2)
        
        # 삭제파일
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass
    
    async def handle_interview(self, command_id: str, agent_id: int, prompt: str) -> bool:
        """
        에이전트 단건 인터뷰를 처리한다.
        
        Returns:
            True면 성공, False면 실패
        """
        try:
            # Agent
            agent = self.agent_graph.get_agent(agent_id)
            
            # Interview
            interview_action = ManualAction(
                action_type=ActionType.INTERVIEW,
                action_args={"prompt": prompt}
            )
            
            # Interview
            actions = {agent: interview_action}
            await self.env.step(actions)
            
            # 
            result = self._get_interview_result(agent_id)
            
            self.send_response(command_id, "completed", result=result)
            print(f"  Interview완료: agent_id={agent_id}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"  Interview실패: agent_id={agent_id}, error={error_msg}")
            self.send_response(command_id, "failed", error=error_msg)
            return False
    
    async def handle_batch_interview(self, command_id: str, interviews: List[Dict]) -> bool:
        """
        인터뷰
        
        Args:
            interviews: [{"agent_id": int, "prompt": str}, ...]
        """
        try:
            # 
            actions = {}
            agent_prompts = {}  # agentprompt
            
            for interview in interviews:
                agent_id = interview.get("agent_id")
                prompt = interview.get("prompt", "")
                
                try:
                    agent = self.agent_graph.get_agent(agent_id)
                    actions[agent] = ManualAction(
                        action_type=ActionType.INTERVIEW,
                        action_args={"prompt": prompt}
                    )
                    agent_prompts[agent_id] = prompt
                except Exception as e:
                    print(f"  경고: Agent {agent_id}: {e}")
            
            if not actions:
                self.send_response(command_id, "failed", error="유효Agent")
                return False
            
            # Interview
            await self.env.step(actions)
            
            # 
            results = {}
            for agent_id in agent_prompts.keys():
                result = self._get_interview_result(agent_id)
                results[agent_id] = result
            
            self.send_response(command_id, "completed", result={
                "interviews_count": len(results),
                "results": results
            })
            print(f"  Interview완료: {len(results)}개Agent")
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"  Interview실패: {error_msg}")
            self.send_response(command_id, "failed", error=error_msg)
            return False
    
    def _get_interview_result(self, agent_id: int) -> Dict[str, Any]:
        """Interview"""
        db_path = os.path.join(self.simulation_dir, "twitter_simulation.db")
        
        result = {
            "agent_id": agent_id,
            "response": None,
            "timestamp": None
        }
        
        if not os.path.exists(db_path):
            return result
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 조회Interview
            cursor.execute("""
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (ActionType.INTERVIEW.value, agent_id))
            
            row = cursor.fetchone()
            if row:
                user_id, info_json, created_at = row
                try:
                    info = json.loads(info_json) if info_json else {}
                    result["response"] = info.get("response", info)
                    result["timestamp"] = created_at
                except json.JSONDecodeError:
                    result["response"] = info_json
            
            conn.close()
            
        except Exception as e:
            print(f"  읽기Interview실패: {e}")
        
        return result
    
    async def process_commands(self) -> bool:
        """
        
        
        Returns:
            True 실행, False 
        """
        command = self.poll_command()
        if not command:
            return True
        
        command_id = command.get("command_id")
        command_type = command.get("command_type")
        args = command.get("args", {})
        
        print(f"\nIPC: {command_type}, id={command_id}")
        
        if command_type == CommandType.INTERVIEW:
            await self.handle_interview(
                command_id,
                args.get("agent_id", 0),
                args.get("prompt", "")
            )
            return True
            
        elif command_type == CommandType.BATCH_INTERVIEW:
            await self.handle_batch_interview(
                command_id,
                args.get("interviews", [])
            )
            return True
            
        elif command_type == CommandType.CLOSE_ENV:
            print("")
            self.send_response(command_id, "completed", result={"message": ""})
            return False
        
        else:
            self.send_response(command_id, "failed", error=f"타입: {command_type}")
            return True


class TwitterSimulationRunner:
    """Twitter시뮬레이션 실행"""
    
    # Twitter(INTERVIEW, INTERVIEWManualAction)
    AVAILABLE_ACTIONS = [
        ActionType.CREATE_POST,
        ActionType.LIKE_POST,
        ActionType.REPOST,
        ActionType.FOLLOW,
        ActionType.DO_NOTHING,
        ActionType.QUOTE_POST,
    ]
    
    def __init__(self, config_path: str, wait_for_commands: bool = True):
        """
        시뮬레이션 실행
        
        Args:
            config_path: 설정 파일 (simulation_config.json)
            wait_for_commands: 시뮬레이션 완료(True)
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.simulation_dir = os.path.dirname(config_path)
        self.wait_for_commands = wait_for_commands
        self.env = None
        self.agent_graph = None
        self.ipc_handler = None
        
    def _load_config(self) -> Dict[str, Any]:
        """환경 설정 로드 파일"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_profile_path(self) -> str:
        """Profile파일(OASIS TwitterCSV)"""
        return os.path.join(self.simulation_dir, "twitter_profiles.csv")
    
    def _get_db_path(self) -> str:
        """"""
        return os.path.join(self.simulation_dir, "twitter_simulation.db")
    
    def _create_model(self):
        """
        LLM
        
        프로젝트디렉터리 .env 파일 처리 중():
        - LLM_API_KEY: API
        - LLM_BASE_URL: APIURL
        - LLM_MODEL_NAME: 
        """
        #  .env 읽기설정
        provider = os.environ.get("LLM_PROVIDER", "openai_compatible").strip().lower()
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        llm_base_url = os.environ.get("LLM_BASE_URL", "")
        llm_model = os.environ.get("LLM_MODEL_NAME", "")
        
        #  .env 진행 중 config 
        if not llm_model:
            llm_model = self.config.get("llm_model", "gpt-4o-mini")

        print(
            f"LLM?ㅼ젙: provider={provider}, model={llm_model}, "
            f"base_url={llm_base_url[:40] if llm_base_url else ''}..."
        )
        return create_camel_model_backend(
            provider=provider,
            model_name=llm_model,
            api_key=llm_api_key or None,
            base_url=llm_base_url or None,
        )
        
        #  camel-ai 
        if llm_api_key:
            os.environ["OPENAI_API_KEY"] = llm_api_key
        
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("누락 API Key 설정, 프로젝트디렉터리 .env 파일 처리 중LLM_API_KEY")
        
        if llm_base_url:
            os.environ["OPENAI_API_BASE_URL"] = llm_base_url
        
        print(f"LLM설정: model={llm_model}, base_url={llm_base_url[:40] if llm_base_url else ''}...")
        
        return ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI,
            model_type=llm_model,
        )
    
    def _get_active_agents_for_round(
        self, 
        env, 
        current_hour: int,
        round_num: int
    ) -> List:
        """
        설정Agent
        
        Args:
            env: OASIS
            current_hour: 현재시뮬레이션(0-23)
            round_num: 현재
            
        Returns:
            Agent목록
        """
        time_config = self.config.get("time_config", {})
        agent_configs = self.config.get("agent_configs", [])
        
        # 
        base_min = time_config.get("agents_per_hour_min", 5)
        base_max = time_config.get("agents_per_hour_max", 20)
        
        # 
        peak_hours = time_config.get("peak_hours", [9, 10, 11, 14, 15, 20, 21, 22])
        off_peak_hours = time_config.get("off_peak_hours", [0, 1, 2, 3, 4, 5])
        
        if current_hour in peak_hours:
            multiplier = time_config.get("peak_activity_multiplier", 1.5)
        elif current_hour in off_peak_hours:
            multiplier = time_config.get("off_peak_activity_multiplier", 0.3)
        else:
            multiplier = 1.0
        
        target_count = int(random.uniform(base_min, base_max) * multiplier)
        
        # Agent설정
        candidates = []
        for cfg in agent_configs:
            agent_id = cfg.get("agent_id", 0)
            active_hours = cfg.get("active_hours", list(range(8, 23)))
            activity_level = cfg.get("activity_level", 0.5)
            
            # 
            if current_hour not in active_hours:
                continue
            
            # 
            if random.random() < activity_level:
                candidates.append(agent_id)
        
        # 선정
        selected_ids = random.sample(
            candidates, 
            min(target_count, len(candidates))
        ) if candidates else []
        
        # Agent
        active_agents = []
        for agent_id in selected_ids:
            try:
                agent = env.agent_graph.get_agent(agent_id)
                active_agents.append((agent_id, agent))
            except Exception:
                pass
        
        return active_agents
    
    async def run(self, max_rounds: int = None):
        """실행Twitter시뮬레이션
        
        Args:
            max_rounds: 시뮬레이션(선택, 시뮬레이션)
        """
        print("=" * 60)
        print("OASIS Twitter시뮬레이션")
        print(f"설정 파일: {self.config_path}")
        print(f"시뮬레이션ID: {self.config.get('simulation_id', 'unknown')}")
        print(f": {'' if self.wait_for_commands else ''}")
        print("=" * 60)
        
        # 환경 설정 로드
        time_config = self.config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        
        # 
        total_rounds = (total_hours * 60) // minutes_per_round
        
        # , 
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                print(f"\n: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
        
        print(f"\n시뮬레이션 파라미터:")
        print(f"  - 시뮬레이션: {total_hours}")
        print(f"  - : {minutes_per_round}")
        print(f"  - : {total_rounds}")
        if max_rounds:
            print(f"  - : {max_rounds}")
        print(f"  - Agent: {len(self.config.get('agent_configs', []))}")
        
        # 
        print("\nLLM...")
        model = self._create_model()
        
        # 로드Agent
        print("로드Agent Profile...")
        profile_path = self._get_profile_path()
        if not os.path.exists(profile_path):
            print(f"오류: Profile파일존재하지 않음: {profile_path}")
            return
        
        self.agent_graph = await generate_twitter_agent_graph(
            profile_path=profile_path,
            model=model,
            available_actions=self.AVAILABLE_ACTIONS,
        )
        
        # 
        db_path = self._get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"삭제: {db_path}")
        
        # 
        print("OASIS...")
        self.env = oasis.make(
            agent_graph=self.agent_graph,
            platform=oasis.DefaultPlatformType.TWITTER,
            database_path=db_path,
            semaphore=30,  #  LLM 요청,  API 
        )
        
        await self.env.reset()
        print("완료\n")
        
        # IPC
        self.ipc_handler = IPCHandler(self.simulation_dir, self.env, self.agent_graph)
        self.ipc_handler.update_status("running")
        
        # 
        event_config = self.config.get("event_config", {})
        initial_posts = event_config.get("initial_posts", [])
        
        if initial_posts:
            print(f" ({len(initial_posts)})...")
            initial_actions = {}
            for post in initial_posts:
                agent_id = post.get("poster_agent_id", 0)
                content = post.get("content", "")
                try:
                    agent = self.env.agent_graph.get_agent(agent_id)
                    initial_actions[agent] = ManualAction(
                        action_type=ActionType.CREATE_POST,
                        action_args={"content": content}
                    )
                except Exception as e:
                    print(f"  경고: Agent {agent_id}: {e}")
            
            if initial_actions:
                await self.env.step(initial_actions)
                print(f"   {len(initial_actions)}건")
        
        # 시뮬레이션
        print("\n시작시뮬레이션...")
        start_time = datetime.now()
        
        for round_num in range(total_rounds):
            # 현재시뮬레이션
            simulated_minutes = round_num * minutes_per_round
            simulated_hour = (simulated_minutes // 60) % 24
            simulated_day = simulated_minutes // (60 * 24) + 1
            
            # Agent
            active_agents = self._get_active_agents_for_round(
                self.env, simulated_hour, round_num
            )
            
            if not active_agents:
                continue
            
            # 
            actions = {
                agent: LLMAction()
                for _, agent in active_agents
            }
            
            # 
            await self.env.step(actions)
            
            # 진행률
            if (round_num + 1) % 10 == 0 or round_num == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = (round_num + 1) / total_rounds * 100
                print(f"  [Day {simulated_day}, {simulated_hour:02d}:00] "
                      f"Round {round_num + 1}/{total_rounds} ({progress:.1f}%) "
                      f"- {len(active_agents)} agents active "
                      f"- elapsed: {elapsed:.1f}s")
        
        total_elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n시뮬레이션 완료!")
        print(f"  - : {total_elapsed:.1f}")
        print(f"  - : {db_path}")
        
        # 
        if self.wait_for_commands:
            print("\n" + "=" * 60)
            print(" - 실행")
            print(": interview, batch_interview, close_env")
            print("=" * 60)
            
            self.ipc_handler.update_status("alive")
            
            # ( _shutdown_event)
            try:
                while not _shutdown_event.is_set():
                    should_continue = await self.ipc_handler.process_commands()
                    if not should_continue:
                        break
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=0.5)
                        break  # 
                    except asyncio.TimeoutError:
                        pass
            except KeyboardInterrupt:
                print("\n사용자 인터럽트로 종료를 시작합니다.")
            except asyncio.CancelledError:
                print("\n작업이 취소되었습니다.")
            except Exception as e:
                print(f"\n실행 중 오류가 발생했습니다: {e}")
            
            print("\n시뮬레이션 종료 절차를 진행합니다.")
        
        # 
        self.ipc_handler.update_status("stopped")
        await self.env.close()
        
        print("")
        print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description='OASIS Twitter 시뮬레이션 실행')
    parser.add_argument(
        '--config', 
        type=str, 
        required=True,
        help='설정 파일 경로 (simulation_config.json)'
    )
    parser.add_argument(
        '--max-rounds',
        type=int,
        default=None,
        help='최대 라운드 수(선택, 기본: 설정 파일 값)'
    )
    parser.add_argument(
        '--no-wait',
        action='store_true',
        default=False,
        help='시뮬레이션 종료 후 IPC 대기 없이 바로 종료'
    )
    
    args = parser.parse_args()
    
    #  main 시작 shutdown 
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    
    if not os.path.exists(args.config):
        print(f"오류: 설정 파일이 존재하지 않습니다: {args.config}")
        sys.exit(1)
    
    # 로그 설정
    simulation_dir = os.path.dirname(args.config) or "."
    setup_oasis_logging(os.path.join(simulation_dir, "log"))
    
    runner = TwitterSimulationRunner(
        config_path=args.config,
        wait_for_commands=not args.no_wait
    )
    await runner.run(max_rounds=args.max_rounds)


def setup_signal_handlers():
    """
    SIGTERM/SIGINT 시그널 핸들러를 설정한다.
    안전한 종료를 위한 이벤트를 전달한다.
    """
    def signal_handler(signum, frame):
        global _cleanup_done
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\n{sig_name} 신호 수신, 종료 처리 진행 중")
        if not _cleanup_done:
            _cleanup_done = True
            if _shutdown_event:
                _shutdown_event.set()
        else:
            print("강제 종료합니다.")
            sys.exit(1)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    setup_signal_handlers()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n사용자 인터럽트로 종료합니다.")
    except SystemExit:
        pass
    finally:
        print("시뮬레이션 종료")
