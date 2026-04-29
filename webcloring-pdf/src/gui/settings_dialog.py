"""
설정 다이얼로그
사용자 인증 정보, 검색 날짜, 스케줄 등을 설정
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, time
import os
from pathlib import Path

from config.settings import settings


class SettingsDialog:
    """설정 다이얼로그 클래스"""
    
    def __init__(self, parent):
        self.parent = parent
        self.result = False
        
        # 현재 설정값 로드
        self.load_current_settings()
        
        # 다이얼로그 생성
        self.create_dialog()
        
    def load_current_settings(self):
        """현재 설정값 로드"""
        try:
            self.username = settings.portal_username
            self.password = settings.portal_password
            self.search_keyword = settings.search_keyword
            self.search_date = settings.search_start_date
            self.auto_enabled = settings.auto_enabled
            self.schedule_time = settings.schedule_time
            self.weekdays_only = settings.weekdays_only
            self.dynamic_filtering = settings.dynamic_filtering
            self.days_back = settings.days_back
        except Exception as e:
            print(f"설정 로드 오류: {e}")
            # 기본값 설정
            self.username = ""
            self.password = ""
            self.search_keyword = "자재"
            self.search_date = datetime.now().strftime('%Y.%m.%d')
            self.auto_enabled = True
            self.schedule_time = "09:00"
            self.weekdays_only = False
            self.dynamic_filtering = True
            self.days_back = 0
    
    def create_dialog(self):
        """다이얼로그 창 생성"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("설정")
        self.dialog.geometry("400x550")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 중앙 정렬
        self.dialog.geometry(f"+{self.parent.winfo_rootx()+50}+{self.parent.winfo_rooty()+50}")
        
        self.create_widgets()
        
        # Enter 키로 저장
        self.dialog.bind('<Return>', lambda e: self.save_settings())
        
        # 포커스 설정
        if not self.username:
            self.username_entry.focus()
        elif not self.password:
            self.password_entry.focus()
        
        # 모달 대화상자로 만들기
        self.dialog.wait_window()
    
    def create_widgets(self):
        """위젯 생성"""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 로그인 정보 섹션
        login_frame = ttk.LabelFrame(main_frame, text="로그인 정보", padding="10")
        login_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(login_frame, text="사용자명:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.username_entry = ttk.Entry(login_frame, width=30)
        self.username_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))
        self.username_entry.insert(0, self.username)
        
        ttk.Label(login_frame, text="비밀번호:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(5, 0))
        self.password_entry = ttk.Entry(login_frame, width=30, show="*")
        self.password_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(5, 0))
        self.password_entry.insert(0, self.password)
        
        login_frame.columnconfigure(1, weight=1)
        
        # 검색 설정 섹션
        search_frame = ttk.LabelFrame(main_frame, text="검색 설정", padding="10")
        search_frame.pack(fill=tk.X, pady=(0, 10))

        # 검색 키워드 입력
        ttk.Label(search_frame, text="검색 키워드:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.keyword_entry = ttk.Entry(search_frame, width=15)
        self.keyword_entry.grid(row=0, column=1, sticky=tk.W)
        self.keyword_entry.insert(0, self.search_keyword)

        ttk.Label(search_frame, text="시작 날짜:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(5, 0))

        date_frame = ttk.Frame(search_frame)
        date_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(5, 0))
        
        self.date_entry = ttk.Entry(date_frame, width=12)
        self.date_entry.grid(row=0, column=0)
        self.date_entry.insert(0, self.search_date)
        
        ttk.Label(date_frame, text="(YYYY.MM.DD 형식)").grid(row=0, column=1, padx=(5, 0))
        
        # 동적 필터링 옵션
        self.dynamic_var = tk.BooleanVar(value=self.dynamic_filtering)
        dynamic_check = ttk.Checkbutton(search_frame, text="스마트 필터링 사용 (마지막 문서 날짜부터 자동 검색)",
                                       variable=self.dynamic_var, command=self.toggle_date_options)
        dynamic_check.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))

        # 여분 날짜 설정
        days_frame = ttk.Frame(search_frame)
        days_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Label(days_frame, text="여분 검색 일수:").grid(row=0, column=0, sticky=tk.W, padx=(20, 10))
        
        self.days_back_var = tk.IntVar(value=self.days_back)
        days_spin = ttk.Spinbox(days_frame, from_=0, to=7, width=5, textvariable=self.days_back_var)
        days_spin.grid(row=0, column=1)
        
        ttk.Label(days_frame, text="일 전부터 (놓칠 수 있는 문서 고려)").grid(row=0, column=2, padx=(5, 0))
        
        # 위젯 저장 (나중에 enable/disable 하기 위해)
        self.date_widgets = [self.date_entry, days_spin]
        
        search_frame.columnconfigure(1, weight=1)
        
        # 자동 실행 설정 섹션
        schedule_frame = ttk.LabelFrame(main_frame, text="자동 실행 스케줄", padding="10")
        schedule_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.auto_var = tk.BooleanVar(value=self.auto_enabled)
        auto_check = ttk.Checkbutton(schedule_frame, text="자동 실행 사용", variable=self.auto_var,
                                    command=self.toggle_schedule_options)
        auto_check.grid(row=0, column=0, columnspan=2, sticky=tk.W)
        
        ttk.Label(schedule_frame, text="실행 시간:").grid(row=1, column=0, sticky=tk.W, padx=(20, 10), pady=(5, 0))
        
        time_frame = ttk.Frame(schedule_frame)
        time_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # 시간 입력
        self.hour_var = tk.StringVar(value=self.schedule_time.split(':')[0])
        self.minute_var = tk.StringVar(value=self.schedule_time.split(':')[1])
        
        hour_spin = ttk.Spinbox(time_frame, from_=0, to=23, width=3, textvariable=self.hour_var, format="%02.0f")
        hour_spin.grid(row=0, column=0)
        
        ttk.Label(time_frame, text=":").grid(row=0, column=1)
        
        minute_spin = ttk.Spinbox(time_frame, from_=0, to=59, width=3, textvariable=self.minute_var, format="%02.0f")
        minute_spin.grid(row=0, column=2)
        
        ttk.Label(time_frame, text="매일").grid(row=0, column=3, padx=(5, 0))
        
        # 평일만 옵션
        self.weekdays_var = tk.BooleanVar(value=self.weekdays_only)
        weekdays_check = ttk.Checkbutton(schedule_frame, text="평일만 실행 (월-금)", 
                                        variable=self.weekdays_var)
        weekdays_check.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=(5, 0))
        
        # 헤드리스 모드 옵션 추가
        self.headless_var = tk.BooleanVar(value=settings.headless_mode)
        headless_check = ttk.Checkbutton(schedule_frame, text="헤드리스 모드 (백그라운드 실행)",
                                         variable=self.headless_var)
        headless_check.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        schedule_frame.columnconfigure(1, weight=1)
        
        # 스케줄 옵션 저장 (나중에 enable/disable 하기 위해)
        self.schedule_widgets = [hour_spin, minute_spin, weekdays_check, headless_check]
        
        # 초기 상태 설정
        self.toggle_schedule_options()
        self.toggle_date_options()
        
        # 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="테스트 실행", command=self.test_connection).pack(side=tk.LEFT)
        
        ttk.Button(button_frame, text="취소", command=self.cancel).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="저장", command=self.save_settings).pack(side=tk.RIGHT)
    
    def toggle_schedule_options(self):
        """스케줄 옵션 활성화/비활성화"""
        state = 'normal' if self.auto_var.get() else 'disabled'
        for widget in self.schedule_widgets:
            widget.config(state=state)
    
    def toggle_date_options(self):
        """날짜 옵션 활성화/비활성화"""
        # 스마트 필터링이 OFF일 때만 수동 날짜 입력 활성화
        manual_date_state = 'normal' if not self.dynamic_var.get() else 'disabled'
        # 스마트 필터링이 ON일 때만 여분 일수 설정 활성화
        days_back_state = 'normal' if self.dynamic_var.get() else 'disabled'
        
        self.date_entry.config(state=manual_date_state)
        self.date_widgets[1].config(state=days_back_state)  # days_spin
    
    def test_connection(self):
        """연결 테스트"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username or not password:
            messagebox.showwarning("경고", "사용자명과 비밀번호를 입력해주세요.")
            return
        
        # 임시로 환경변수 설정
        original_username = os.getenv('PORTAL_USERNAME')
        original_password = os.getenv('PORTAL_PASSWORD')
        
        os.environ['PORTAL_USERNAME'] = username
        os.environ['PORTAL_PASSWORD'] = password
        
        try:
            from core.portal_automation import PortalAutomation
            
            # 로그인 테스트만 수행
            automation = PortalAutomation()
            automation.setup_driver()
            
            success = automation.login_to_portal()
            
            if success:
                messagebox.showinfo("성공", "로그인 테스트가 성공했습니다!")
            else:
                messagebox.showerror("실패", "로그인에 실패했습니다. 인증 정보를 확인해주세요.")
            
            # 브라우저 정리
            if automation.driver:
                automation.driver.quit()
                
        except Exception as e:
            messagebox.showerror("오류", f"테스트 중 오류가 발생했습니다:\\n{str(e)}")
        
        finally:
            # 환경변수 복원
            if original_username:
                os.environ['PORTAL_USERNAME'] = original_username
            if original_password:
                os.environ['PORTAL_PASSWORD'] = original_password
    
    def save_settings(self):
        """모든 설정을 .env 파일에 저장"""
        try:
            # 입력값 검증
            if not self.username_entry.get().strip():
                messagebox.showwarning("경고", "사용자명을 입력해주세요.")
                self.username_entry.focus()
                return

            if not self.password_entry.get().strip():
                messagebox.showwarning("경고", "비밀번호를 입력해주세요.")
                self.password_entry.focus()
                return

            if not self.keyword_entry.get().strip():
                messagebox.showwarning("경고", "검색 키워드를 입력해주세요.")
                self.keyword_entry.focus()
                return

            try:
                datetime.strptime(self.date_entry.get().strip(), '%Y.%m.%d')
            except ValueError:
                messagebox.showwarning("경고", "시작 날짜 형식이 올바르지 않습니다. (YYYY.MM.DD)")
                self.date_entry.focus()
                return

            # UI에서 모든 설정값 수집
            new_settings = {
                'PORTAL_USERNAME': self.username_entry.get().strip(),
                'PORTAL_PASSWORD': self.password_entry.get().strip(),
                'SEARCH_KEYWORD': self.keyword_entry.get().strip(),
                'SEARCH_START_DATE': self.date_entry.get().strip(),
                'DYNAMIC_FILTERING': self.dynamic_var.get(),
                'DAYS_BACK': self.days_back_var.get(),
                'AUTO_ENABLED': self.auto_var.get(),
                'SCHEDULE_TIME': f"{self.hour_var.get().zfill(2)}:{self.minute_var.get().zfill(2)}",
                'WEEKDAYS_ONLY': self.weekdays_var.get(),
                'HEADLESS_MODE': self.headless_var.get()
            }
            
            # 중앙화된 저장 메소드 호출
            settings.save_env_settings(new_settings)
            
            messagebox.showinfo("완료", "설정이 저장되었습니다.")
            self.result = True
            self.dialog.destroy()
            
        except Exception as e:
            messagebox.showerror("오류", f"설정 저장 중 오류가 발생했습니다:\\n{str(e)}")

    def cancel(self):
        """취소"""
        self.dialog.destroy()


if __name__ == "__main__":
    # 테스트용
    root = tk.Tk()
    root.withdraw()  # 메인 창 숨기기
    dialog = SettingsDialog(root)
    root.destroy()