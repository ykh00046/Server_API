"""
구글 시트 백업 설정 다이얼로그 - v3.0
tkinter 기반 GUI with Threading

주요 개선사항 (v3.0):
- Threading: 모든 네트워크 작업을 백그라운드 스레드에서 실행하여 GUI 프리징 방지
- Thread-Safe: dialog.after()를 사용하여 메인 스레드로 GUI 업데이트
- User Feedback: 버튼 상태 변경 및 진행 상황 표시
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional
from utils.logger import logger
from src.services.google_sheets_manager import GoogleSheetsManager, create_credentials_guide


class GoogleSheetsDialog:
    """구글 시트 백업 설정 다이얼로그"""

    def __init__(self, parent, excel_manager=None):
        """초기화

        Args:
            parent: 부모 윈도우
            excel_manager: ExcelManager 인스턴스 (백업 실행 시 사용)
        """
        self.parent = parent
        self.excel_manager = excel_manager

        # 부모가 backup_manager를 가지고 있으면 사용, 아니면 새로 생성
        if hasattr(parent, 'backup_manager'):
            self.backup_manager = parent.backup_manager
        else:
            self.backup_manager = GoogleSheetsManager()

        # 다이얼로그 생성
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("구글 시트 백업 설정")
        self.dialog.geometry("700x600")
        self.dialog.resizable(False, False)

        # 초기화
        self.init_ui()
        self.load_current_settings()

        # 모달 설정
        self.dialog.transient(parent)
        self.dialog.grab_set()

    def init_ui(self):
        """UI 초기화"""
        # 메인 프레임
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 제목
        title_label = ttk.Label(
            main_frame,
            text="📊 구글 시트 백업 설정",
            font=("맑은 고딕", 14, "bold")
        )
        title_label.pack(pady=(0, 10))

        # 1. 연결 설정 영역
        self._create_connection_section(main_frame)

        # 2. 백업 실행 영역
        self._create_backup_section(main_frame)

        # 3. 가이드 영역
        self._create_guide_section(main_frame)

        # 4. 닫기 버튼
        close_btn = ttk.Button(
            main_frame,
            text="닫기",
            command=self.dialog.destroy
        )
        close_btn.pack(pady=(10, 0))

    def _create_connection_section(self, parent):
        """연결 설정 영역 생성"""
        # 프레임
        conn_frame = ttk.LabelFrame(parent, text="연결 설정", padding="10")
        conn_frame.pack(fill=tk.BOTH, pady=(0, 10))

        # JSON 인증 파일
        cred_frame = ttk.Frame(conn_frame)
        cred_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(cred_frame, text="JSON 인증 파일:", width=15).pack(side=tk.LEFT)
        self.credentials_entry = ttk.Entry(cred_frame)
        self.credentials_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        browse_btn = ttk.Button(
            cred_frame,
            text="찾아보기",
            command=self.browse_credentials_file,
            width=10
        )
        browse_btn.pack(side=tk.LEFT)

        # 구글 시트 URL
        url_frame = ttk.Frame(conn_frame)
        url_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(url_frame, text="구글 시트 URL:", width=15).pack(side=tk.LEFT)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 연결 테스트 버튼 (v3.0: Threading 적용)
        self.test_btn = ttk.Button(
            conn_frame,
            text="🔍 연결 테스트",
            command=self.test_connection
        )
        self.test_btn.pack(pady=(5, 5))

        # 연결 상태 표시
        self.status_label = ttk.Label(
            conn_frame,
            text="연결 상태: 미연결",
            foreground="red",
            font=("맑은 고딕", 9, "bold")
        )
        self.status_label.pack()

    def _create_backup_section(self, parent):
        """백업 실행 영역 생성"""
        backup_frame = ttk.LabelFrame(parent, text="백업 실행", padding="10")
        backup_frame.pack(fill=tk.BOTH, pady=(0, 10))

        # 안내 메시지
        info_label = ttk.Label(
            backup_frame,
            text="💡 현재 Excel 파일의 모든 자재 데이터를 구글 시트에 백업합니다.",
            foreground="gray"
        )
        info_label.pack(pady=(0, 10))

        # 버튼들
        btn_frame = ttk.Frame(backup_frame)
        btn_frame.pack(fill=tk.X)

        # 전체 백업 버튼 (v3.0: Threading 적용)
        self.backup_btn = ttk.Button(
            btn_frame,
            text="📤 전체 백업 실행",
            command=self.run_backup,
            state=tk.DISABLED
        )
        self.backup_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        # 샘플 데이터 테스트 (v3.0: Threading 적용)
        sample_btn = ttk.Button(
            btn_frame,
            text="📝 샘플 데이터 테스트",
            command=self.create_sample_data
        )
        sample_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

    def _create_guide_section(self, parent):
        """가이드 영역 생성"""
        guide_frame = ttk.LabelFrame(parent, text="📋 설정 가이드", padding="10")
        guide_frame.pack(fill=tk.BOTH, expand=True)

        guide_btn = ttk.Button(
            guide_frame,
            text="📖 구글 API 설정 가이드 보기",
            command=self.show_setup_guide
        )
        guide_btn.pack()

    def load_current_settings(self):
        """현재 설정값을 UI에 로드"""
        try:
            # 저장된 설정 로드
            credentials_file = self.backup_manager.config.get_credentials_file()
            spreadsheet_url = self.backup_manager.config.get_spreadsheet_url()

            # UI에 설정값 표시
            if credentials_file:
                self.credentials_entry.insert(0, credentials_file)
            if spreadsheet_url:
                self.url_entry.insert(0, spreadsheet_url)

            # 연결 상태 확인
            if self.backup_manager.is_connected:
                test_result = self.backup_manager.test_connection()
                if test_result['success']:
                    self.status_label.config(
                        text=f"✅ 연결됨: {test_result['spreadsheet_name']}",
                        foreground="green"
                    )
                    self.backup_btn.config(state=tk.NORMAL)
                else:
                    self.status_label.config(
                        text=f"❌ 연결 실패: {test_result['message']}",
                        foreground="red"
                    )
            else:
                self.status_label.config(
                    text="연결 상태: 미연결",
                    foreground="red"
                )

        except Exception as e:
            logger.error(f"설정 로드 오류: {e}")

    def browse_credentials_file(self):
        """JSON 인증 파일 선택"""
        file_path = filedialog.askopenfilename(
            parent=self.dialog,
            title="JSON 인증 파일 선택",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if file_path:
            self.credentials_entry.delete(0, tk.END)
            self.credentials_entry.insert(0, file_path)

    def test_connection(self):
        """연결 테스트 (v3.0: Threading 적용)"""
        credentials_file = self.credentials_entry.get().strip()
        sheet_url = self.url_entry.get().strip()

        if not credentials_file or not sheet_url:
            messagebox.showwarning(
                "입력 오류",
                "JSON 파일과 구글 시트 URL을 모두 입력해주세요.",
                parent=self.dialog
            )
            return

        # UI 상태 변경 (메인 스레드)
        self.test_btn.config(state=tk.DISABLED, text="연결 중...")
        self.status_label.config(text="연결 중...", foreground="orange")
        self.dialog.update()

        # 백그라운드 스레드에서 연결 테스트 실행 ✅
        thread = threading.Thread(
            target=self._test_connection_thread,
            args=(credentials_file, sheet_url),
            daemon=True
        )
        thread.start()

    def _test_connection_thread(self, credentials_file: str, sheet_url: str):
        """연결 테스트 실행 (백그라운드 스레드)"""
        try:
            # 네트워크 작업 (백그라운드에서 실행)
            success = self.backup_manager.setup_connection(credentials_file, sheet_url)

            # 결과를 메인 스레드로 전달 ✅
            self.dialog.after(0, lambda: self._on_connection_test_complete(success))

        except Exception as e:
            logger.error(f"연결 테스트 스레드 오류: {e}")
            self.dialog.after(0, lambda: self._on_connection_test_error(str(e)))

    def _on_connection_test_complete(self, success: bool):
        """연결 테스트 완료 처리 (메인 스레드)"""
        # UI 상태 복원
        self.test_btn.config(state=tk.NORMAL, text="🔍 연결 테스트")

        if success:
            # 연결 정보 확인
            test_result = self.backup_manager.test_connection()
            if test_result['success']:
                self.status_label.config(
                    text=f"✅ 연결 성공: {test_result['spreadsheet_name']}",
                    foreground="green"
                )
                self.backup_btn.config(state=tk.NORMAL)

                messagebox.showinfo(
                    "연결 성공",
                    f"구글 시트 연결에 성공했습니다!\n\n"
                    f"스프레드시트: {test_result['spreadsheet_name']}\n"
                    f"워크시트: {test_result['worksheet_name']}",
                    parent=self.dialog
                )
            else:
                self.status_label.config(
                    text=f"❌ 연결 실패: {test_result['message']}",
                    foreground="red"
                )
        else:
            self.status_label.config(text="❌ 연결 실패", foreground="red")
            messagebox.showerror(
                "연결 실패",
                "구글 시트 연결에 실패했습니다.\n설정을 확인해주세요.",
                parent=self.dialog
            )

    def _on_connection_test_error(self, error_msg: str):
        """연결 테스트 오류 처리 (메인 스레드)"""
        self.test_btn.config(state=tk.NORMAL, text="🔍 연결 테스트")
        self.status_label.config(text="❌ 연결 오류", foreground="red")
        messagebox.showerror(
            "연결 오류",
            f"연결 중 오류가 발생했습니다:\n{error_msg}",
            parent=self.dialog
        )

    def run_backup(self):
        """백업 실행 (v3.0: Threading 적용)"""
        if not self.backup_manager.is_connected:
            messagebox.showwarning(
                "연결 오류",
                "먼저 구글 시트에 연결해주세요.",
                parent=self.dialog
            )
            return

        if not self.excel_manager:
            messagebox.showerror(
                "오류",
                "ExcelManager가 초기화되지 않았습니다.",
                parent=self.dialog
            )
            return

        # 확인 메시지
        reply = messagebox.askyesno(
            "백업 확인",
            "모든 자재 데이터를 구글 시트에 백업하시겠습니까?\n\n"
            "기존 시트의 데이터는 모두 삭제되고 새로운 데이터로 대체됩니다.",
            parent=self.dialog
        )

        if not reply:
            return

        # UI 상태 변경 (메인 스레드)
        self.backup_btn.config(state=tk.DISABLED, text="백업 중...")
        self.dialog.update()

        # 백그라운드 스레드에서 백업 실행 ✅
        thread = threading.Thread(
            target=self._run_backup_thread,
            daemon=True
        )
        thread.start()

    def _run_backup_thread(self):
        """백업 실행 (백그라운드 스레드)"""
        try:
            # 네트워크 작업 (백그라운드에서 실행)
            success = self.backup_manager.backup_materials(self.excel_manager, silent=False)

            # 결과를 메인 스레드로 전달 ✅
            self.dialog.after(0, lambda: self._on_backup_complete(success))

        except Exception as e:
            logger.error(f"백업 스레드 오류: {e}")
            self.dialog.after(0, lambda: self._on_backup_error(str(e)))

    def _on_backup_complete(self, success: bool):
        """백업 완료 처리 (메인 스레드)"""
        # UI 상태 복원
        self.backup_btn.config(state=tk.NORMAL, text="📤 전체 백업 실행")

        if success:
            # 부모 윈도우의 백업 상태도 업데이트
            if hasattr(self.parent, 'update_backup_status'):
                self.parent.update_backup_status()

            messagebox.showinfo(
                "백업 완료",
                "자재 데이터가 구글 시트에 성공적으로 백업되었습니다!",
                parent=self.dialog
            )
        else:
            messagebox.showerror(
                "백업 실패",
                "백업 중 오류가 발생했습니다.\n로그를 확인해주세요.",
                parent=self.dialog
            )

    def _on_backup_error(self, error_msg: str):
        """백업 오류 처리 (메인 스레드)"""
        self.backup_btn.config(state=tk.NORMAL, text="📤 전체 백업 실행")
        messagebox.showerror(
            "백업 오류",
            f"백업 중 오류가 발생했습니다:\n{error_msg}",
            parent=self.dialog
        )

    def create_sample_data(self):
        """샘플 데이터 생성 (v3.0: Threading 적용)"""
        if not self.backup_manager.is_connected:
            messagebox.showwarning(
                "연결 오류",
                "먼저 구글 시트에 연결해주세요.",
                parent=self.dialog
            )
            return

        # 백그라운드 스레드에서 실행 ✅
        thread = threading.Thread(
            target=self._create_sample_data_thread,
            daemon=True
        )
        thread.start()

    def _create_sample_data_thread(self):
        """샘플 데이터 생성 (백그라운드 스레드)"""
        try:
            success = self.backup_manager.create_sample_data()
            self.dialog.after(0, lambda: self._on_sample_data_complete(success))
        except Exception as e:
            logger.error(f"샘플 데이터 생성 오류: {e}")
            self.dialog.after(0, lambda: self._on_sample_data_error(str(e)))

    def _on_sample_data_complete(self, success: bool):
        """샘플 데이터 생성 완료 (메인 스레드)"""
        if success:
            messagebox.showinfo(
                "샘플 데이터 생성",
                "샘플 데이터가 구글 시트에 생성되었습니다!\n연결 테스트가 완료되었습니다.",
                parent=self.dialog
            )
        else:
            messagebox.showerror(
                "샘플 데이터 실패",
                "샘플 데이터 생성에 실패했습니다.",
                parent=self.dialog
            )

    def _on_sample_data_error(self, error_msg: str):
        """샘플 데이터 오류 (메인 스레드)"""
        messagebox.showerror(
            "오류",
            f"샘플 데이터 생성 중 오류:\n{error_msg}",
            parent=self.dialog
        )

    def show_setup_guide(self):
        """설정 가이드 표시"""
        guide_dialog = tk.Toplevel(self.dialog)
        guide_dialog.title("구글 API 설정 가이드")
        guide_dialog.geometry("750x650")

        # 가이드 텍스트
        text_widget = scrolledtext.ScrolledText(
            guide_dialog,
            wrap=tk.WORD,
            font=("Consolas", 10),
            padx=10,
            pady=10
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(tk.END, create_credentials_guide())
        text_widget.config(state=tk.DISABLED)

        # 닫기 버튼
        close_btn = ttk.Button(
            guide_dialog,
            text="닫기",
            command=guide_dialog.destroy
        )
        close_btn.pack(pady=(0, 10))

        # 모달 설정
        guide_dialog.transient(self.dialog)
        guide_dialog.grab_set()
