"""
MiroFish Backend - Flask 애플리케이션 팩토리
"""

import os
import warnings
from pathlib import Path

# `multiprocessing resource_tracker` 경고 억제(transformers 등 서드파티 라이브러리에서 발생)
# 다른 import보다 먼저 설정해야 함
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request, send_from_directory
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask 애플리케이션 팩토리 함수"""
    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    static_folder = str(frontend_dist) if frontend_dist.exists() else None
    app = Flask(__name__, static_folder=static_folder, static_url_path="")
    app.config.from_object(config_class)
    
    # JSON 인코딩 설정: 문자를 `\uXXXX` 형태가 아닌 원문으로 반환
    # Flask >= 2.3 은 app.json.ensure_ascii, 구버전은 JSON_AS_ASCII 사용
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # 로거 설정
    logger = setup_logger('mirofish')
    
    # debug 모드에서 중복 출력되지 않도록 reloader 서브프로세스에서만 시작 로그 출력
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend 시작 중...")
        logger.info("=" * 50)
    
    # CORS 활성화
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # 시뮬레이션 프로세스 정리 함수 등록(서버 종료 시 모든 시뮬레이션 프로세스 종료)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("시뮬레이션 프로세스 정리 함수 등록 완료")
    
    # 요청/응답 로깅 미들웨어
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"요청: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"요청 본문: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"응답: {response.status_code}")
        return response
    
    # 블루프린트 등록
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    
    # 헬스 체크
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path: str):
        """Serve the built SPA when present, falling back to index.html."""
        if not app.static_folder:
            return {'status': 'ok', 'service': 'MiroFish Backend', 'frontend': 'not_built'}

        requested_path = Path(app.static_folder) / path
        if path and requested_path.is_file():
            return send_from_directory(app.static_folder, path)

        index_file = Path(app.static_folder) / 'index.html'
        if index_file.exists():
            return send_from_directory(app.static_folder, 'index.html')

        return {'status': 'ok', 'service': 'MiroFish Backend', 'frontend': 'missing_index'}
    
    if should_log_startup:
        logger.info("MiroFish Backend 시작 완료")
    
    return app
