"""
INTEROJO 자동화 GUI 메인 창
기존 자동화 코드와 연동하여 사용자 친화적인 인터페이스 제공
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트 (로그 디렉토리 참조용)
project_root = Path(__file__).parent.parent

from core.portal_automation import PortalAutomation
from core.scheduler import ServiceScheduler
from config.settings import settings
from utils.logger import logger

# Google Sheets 통합
try:
    from src.gui.google_sheets_dialog import GoogleSheetsDialog
    GOOGLE_SHEETS_GUI_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_GUI_AVAILABLE = False
    logger.debug("Google Sheets GUI를 사용할 수 없습니다")


class AutomationGUI:
    """자동화 GUI 메인 클래스"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.automation = None
        self.is_running = False
        self.auto_mode = False
        self.scheduler = None
        self.next_scheduled_time = None
        
        self.setup_window()
        self.create_widgets()
        self.update_status()
        
    def setup_window(self):
        """윈도우 기본 설정"""
        self.root.title("INTEROJO 자동화 관리 시스템 v1.0")
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        
        # 아이콘 설정 (선택사항)
        try:
            # self.root.iconbitmap("icon.ico")  # 아이콘 파일이 있다면
            pass
        except:
            pass
    
    def create_widgets(self):
        """GUI 위젯 생성"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 제목
        title_label = ttk.Label(main_frame, text="INTEROJO 포털 자동화", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # 상태 표시 프레임
        status_frame = ttk.LabelFrame(main_frame, text="현재 상태", padding="10")
        status_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.status_label = ttk.Label(status_frame, text="상태: 대기 중")
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        self.last_run_label = ttk.Label(status_frame, text="마지막 실행: -")
        self.last_run_label.grid(row=1, column=0, sticky=tk.W)
        
        self.next_run_label = ttk.Label(status_frame, text="다음 실행: -")
        self.next_run_label.grid(row=2, column=0, sticky=tk.W)
        
        # 실행 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        self.run_now_btn = ttk.Button(button_frame, text="지금 실행하기", 
                                     command=self.run_now, width=15)
        self.run_now_btn.grid(row=0, column=0, padx=5)
        
        self.auto_mode_btn = ttk.Button(button_frame, text="자동 모드 시작", 
                                       command=self.toggle_auto_mode, width=15)
        self.auto_mode_btn.grid(row=0, column=1, padx=5)
        
        # 관리 버튼 프레임
        manage_frame = ttk.Frame(main_frame)
        manage_frame.grid(row=3, column=0, columnspan=2, pady=5)

        ttk.Button(manage_frame, text="설정", command=self.open_settings, width=10).grid(row=0, column=0, padx=5)
        ttk.Button(manage_frame, text="로그 보기", command=self.show_logs, width=10).grid(row=0, column=1, padx=5)
        ttk.Button(manage_frame, text="Excel 열기", command=self.open_excel, width=10).grid(row=0, column=2, padx=5)

        # Google Sheets 버튼 (v3.0)
        if GOOGLE_SHEETS_GUI_AVAILABLE:
            ttk.Button(manage_frame, text="Google Sheets", command=self.open_google_sheets,
                      width=12).grid(row=0, column=3, padx=5)
        
        # 로그 출력 영역
        log_frame = ttk.LabelFrame(main_frame, text="실행 로그", padding="5")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=60)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 그리드 가중치 설정
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
    
    def update_status(self):
        """상태 정보 업데이트"""
        try:
            # 상태 표시
            if self.is_running:
                self.status_label.config(text="상태: 🔄 실행 중")
            elif self.auto_mode:
                self.status_label.config(text="상태: 🟢 자동 모드 활성")
            else:
                self.status_label.config(text="상태: ⏸️ 대기 중")
            
            # 마지막 실행 시간 (Excel 파일 수정 시간으로 추정)
            excel_path = settings.excel_file_path
            if excel_path.exists():
                mtime = datetime.fromtimestamp(excel_path.stat().st_mtime)
                self.last_run_label.config(text=f"마지막 실행: {mtime.strftime('%Y-%m-%d %H:%M')}")
            else:
                self.last_run_label.config(text="마지막 실행: -")
            
            # 다음 실행 시간 (자동 모드일 때만)
            if self.auto_mode and self.scheduler:
                next_time = self._get_next_scheduled_time()
                if next_time:
                    self.next_run_label.config(text=f"다음 실행: {next_time.strftime('%Y-%m-%d %H:%M')}")
                else:
                    self.next_run_label.config(text="다음 실행: 계산 중...")
            else:
                self.next_run_label.config(text="다음 실행: -")
                
        except Exception as e:
            logger.error(f"상태 업데이트 실패: {e}")
        
        # 1초마다 상태 업데이트
        self.root.after(1000, self.update_status)
    
    def run_now(self):
        """즉시 실행"""
        if self.is_running:
            messagebox.showwarning("경고", "이미 실행 중입니다.")
            return
        
        self.run_now_btn.config(state='disabled', text="실행 중...")
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] 자동화 시작\\n")
        
        # 별도 스레드에서 실행
        thread = threading.Thread(target=self._run_automation, daemon=True)
        thread.start()
    
    def _run_automation(self):
        """자동화 실행 (별도 스레드)"""
        try:
            self.is_running = True
            
            # GUI에서 로그 출력을 위한 커스텀 로거 핸들러 추가
            self._setup_gui_logging()
            
            # 기존 자동화 코드 실행
            automation = PortalAutomation()
            success = automation.run_automation()
            
            if success:
                self._log_to_gui("✅ 자동화 완료")
                messagebox.showinfo("완료", "자동화가 성공적으로 완료되었습니다.")
            else:
                self._log_to_gui("❌ 자동화 실패")
                messagebox.showerror("오류", "자동화 중 오류가 발생했습니다. 로그를 확인해주세요.")
            
        except ValueError as e:
            # 설정 오류 (필수 설정 누락 등)
            error_msg = str(e)
            self._log_to_gui(f"❌ 설정 오류: {error_msg}")
            self.root.after(0, lambda: messagebox.showerror(
                "설정 오류",
                f"{error_msg}\n\n설정 화면에서 필수 항목을 확인해주세요."
            ))
        except Exception as e:
            error_msg = str(e)
            self._log_to_gui(f"❌ 오류: {error_msg}")

            # 로그인 오류인 경우 특별 처리
            if "로그인" in error_msg or "인증" in error_msg:
                self.root.after(0, lambda: messagebox.showerror(
                    "로그인 오류",
                    "로그인에 실패했습니다.\\n비밀번호가 변경되었을 수 있습니다.\\n설정을 확인해주세요."
                ))
            else:
                self.root.after(0, lambda: messagebox.showerror("오류", f"예상치 못한 오류: {error_msg}"))
        
        finally:
            self.is_running = False
            self.root.after(0, lambda: self.run_now_btn.config(state='normal', text="지금 실행하기"))
    
    def _setup_gui_logging(self):
        """GUI 로그 출력을 위한 핸들러 설정"""
        import logging
        import queue

        # 로그 메시지 큐 생성
        if not hasattr(self, 'log_queue'):
            self.log_queue = queue.Queue()

        # 커스텀 핸들러 생성
        class QueueHandler(logging.Handler):
            def __init__(self, log_queue):
                super().__init__()
                self.log_queue = log_queue

            def emit(self, record):
                # 로그 메시지를 큐에 추가
                msg = self.format(record)
                self.log_queue.put(msg)

        # logger에 핸들러 추가
        from utils.logger import logger
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
        logger.logger.addHandler(queue_handler)

        # 큐에서 메시지를 읽어 GUI에 표시하는 함수
        def process_log_queue():
            while not self.log_queue.empty():
                try:
                    msg = self.log_queue.get_nowait()
                    self._append_log(msg + '\n')
                except:
                    pass
            # 100ms마다 큐 체크
            if not hasattr(self, '_log_queue_stopped') or not self._log_queue_stopped:
                self.root.after(100, process_log_queue)

        # 큐 처리 시작
        self._log_queue_stopped = False
        process_log_queue()
    
    def _log_to_gui(self, message):
        """GUI 로그 영역에 메시지 출력"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.root.after(0, lambda: self._append_log(f"[{timestamp}] {message}\\n"))
    
    def _append_log(self, message):
        """로그 텍스트 영역에 메시지 추가"""
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
    
    def toggle_auto_mode(self):
        """자동 모드 토글"""
        if not self.auto_mode:
            # 자동 모드 시작
            try:
                self._start_auto_scheduler()
                self.auto_mode = True
                self.auto_mode_btn.config(text="자동 모드 정지")
                self._log_to_gui("🟢 자동 모드 시작")
                
                # 다음 실행 시간 표시
                next_time = self._get_next_scheduled_time()
                if next_time:
                    self._log_to_gui(f"📅 다음 실행: {next_time.strftime('%Y-%m-%d %H:%M')}")
                
                schedule_time = settings.schedule_time
                messagebox.showinfo("자동 모드", f"자동 모드가 시작되었습니다.\\n매일 {schedule_time}에 자동으로 실행됩니다.")
                
            except Exception as e:
                self._log_to_gui(f"❌ 자동 모드 시작 실패: {e}")
                messagebox.showerror("오류", f"자동 모드 시작 실패: {e}")
        else:
            # 자동 모드 정지
            self._stop_auto_scheduler()
            self.auto_mode = False
            self.auto_mode_btn.config(text="자동 모드 시작")
            self._log_to_gui("⏸️ 자동 모드 정지")
            messagebox.showinfo("자동 모드", "자동 모드가 정지되었습니다.")
    
    def _start_auto_scheduler(self):
        """자동 스케줄러 시작"""
        try:
            # 기존 스케줄러가 있으면 정지
            if self.scheduler:
                self.scheduler.stop()
            
            # 새 스케줄러 생성
            self.scheduler = ServiceScheduler()
            
            # 설정된 시간에 실행되도록 스케줄 등록
            schedule_time = settings.schedule_time
            self.scheduler.every(1).day.at(schedule_time).do(self._run_automation_scheduled)
            
            # 스케줄러 시작
            self.scheduler.start()
            
            # 다음 실행 시간 계산
            self.next_scheduled_time = self._get_next_scheduled_time()
            
            self._log_to_gui(f"⏰ 스케줄러 시작됨 (매일 {schedule_time})")
            
        except Exception as e:
            raise Exception(f"스케줄러 시작 실패: {e}")
    
    def _stop_auto_scheduler(self):
        """자동 스케줄러 정지"""
        if self.scheduler:
            try:
                self.scheduler.stop()
                self.scheduler = None
                self.next_scheduled_time = None
                self._log_to_gui("⏰ 스케줄러 정지됨")
            except Exception as e:
                self._log_to_gui(f"⚠️ 스케줄러 정지 중 오류: {e}")
    
    def _run_automation_scheduled(self):
        """스케줄된 자동화 실행"""
        try:
            self._log_to_gui("🤖 자동 실행 시작")
            
            # 실행 중이 아닐 때만 실행
            if not self.is_running:
                # 별도 스레드에서 자동화 실행
                thread = threading.Thread(target=self._run_automation_background, daemon=True)
                thread.start()
            else:
                self._log_to_gui("⚠️ 이미 실행 중이므로 건너뜀")
                
        except Exception as e:
            self._log_to_gui(f"❌ 자동 실행 오류: {e}")
            logger.error(f"자동 실행 오류: {e}")
    
    def _run_automation_background(self):
        """백그라운드 자동화 실행 (스케줄러용)"""
        try:
            self.is_running = True
            self.root.after(0, lambda: self.run_now_btn.config(state='disabled', text="실행 중..."))
            
            automation = PortalAutomation()
            success = automation.run_automation()

            if success:
                self._log_to_gui("✅ 자동 실행 완료")
            else:
                self._log_to_gui("❌ 자동 실행 실패")

        except ValueError as e:
            # 설정 오류 (스케줄 실행 시에는 GUI 알림 없이 로그만)
            error_msg = f"설정 오류: {e}"
            self._log_to_gui(f"❌ {error_msg}")
            logger.error(error_msg)
        except Exception as e:
            self._log_to_gui(f"❌ 자동 실행 오류: {e}")
            logger.error(f"백그라운드 자동화 오류: {e}")
        finally:
            self.is_running = False
            self.root.after(0, lambda: self.run_now_btn.config(state='normal', text="지금 실행하기"))
    
    def _get_next_scheduled_time(self):
        """다음 예정된 실행 시간 계산"""
        if self.scheduler and self.scheduler.jobs:
            try:
                # schedule 라이브러리의 다음 실행 시간 가져오기
                next_run = self.scheduler.jobs[0]['job'].next_run
                return next_run
            except:
                # 수동 계산 - 설정된 시간
                now = datetime.now()
                schedule_time = settings.schedule_time
                hour, minute = map(int, schedule_time.split(':'))
                
                next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # 오늘 설정 시간이 지났으면 내일 같은 시간
                if now >= next_time:
                    next_time += timedelta(days=1)
                
                return next_time
        return None
    
    def open_settings(self):
        """설정 창 열기"""
        from gui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.root)
        if dialog.result:
            self._log_to_gui("⚙️ 설정이 변경되었습니다.")
    
    def show_logs(self):
        """로그 파일 보기"""
        try:
            log_dir = project_root / "logs"
            if log_dir.exists():
                os.startfile(str(log_dir))
            else:
                messagebox.showinfo("알림", "로그 폴더가 없습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"로그 폴더를 열 수 없습니다: {e}")
    
    def open_excel(self):
        """Excel 파일 열기"""
        try:
            excel_path = settings.excel_file_path
            if excel_path.exists():
                os.startfile(str(excel_path))
            else:
                messagebox.showinfo("알림", "Excel 파일이 없습니다.\\n먼저 자동화를 실행해주세요.")
        except Exception as e:
            messagebox.showerror("오류", f"Excel 파일을 열 수 없습니다: {e}")

    def open_google_sheets(self):
        """Google Sheets 설정 창 열기 (v3.0)"""
        if not GOOGLE_SHEETS_GUI_AVAILABLE:
            messagebox.showerror("오류", "Google Sheets 모듈을 사용할 수 없습니다.")
            return

        try:
            # ExcelManager 인스턴스 생성 (백업 실행 시 사용)
            from core.excel_manager import ExcelManager
            excel_manager = ExcelManager()

            # 다이얼로그 열기 (excel_manager 전달)
            dialog = GoogleSheetsDialog(self.root, excel_manager=excel_manager)
            if hasattr(dialog, 'result') and dialog.result:
                self._log_to_gui("📤 Google Sheets 설정이 변경되었습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"Google Sheets 설정을 열 수 없습니다: {e}")
            logger.error(f"Google Sheets 다이얼로그 오류: {e}")

    def run(self):
        """GUI 실행"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
    
    def on_closing(self):
        """창 닫기 이벤트"""
        if self.is_running:
            if not messagebox.askokcancel("종료", "자동화가 실행 중입니다. 정말 종료하시겠습니까?"):
                return
        
        # 스케줄러 정리
        if self.scheduler:
            try:
                self.scheduler.stop()
                self._log_to_gui("🛑 스케줄러 종료됨")
            except Exception as e:
                logger.error(f"스케줄러 종료 중 오류: {e}")
        
        self.root.destroy()


def main():
    """GUI 메인 함수"""
    app = AutomationGUI()
    app.root.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.run()


if __name__ == "__main__":
    main()