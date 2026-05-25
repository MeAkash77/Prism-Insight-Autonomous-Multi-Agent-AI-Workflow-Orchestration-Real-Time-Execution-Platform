import streamlit as st
from datetime import datetime
import re
from pathlib import Path
import markdown
import base64
import sys
import os

# Add current file directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from email_sender import send_email
from queue import Queue
from threading import Thread
import uuid

# Report storage directory
REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Task queue and thread pool setup
analysis_queue = Queue()

class AnalysisRequest:
    def __init__(self, stock_code: str, company_name: str, email: str, reference_date: str):
        self.id = str(uuid.uuid4())
        self.stock_code = stock_code
        self.company_name = company_name
        self.email = email
        self.reference_date = reference_date
        self.status = "pending"
        self.result = None

class ModernStockAnalysisApp:
    def __init__(self):
        self.setup_page()
        self.initialize_session_state()
        self.start_background_worker()

    def setup_page(self):
        """Page setup and custom CSS application"""
        st.set_page_config(
            page_title="analysis.stocksimulation.kr | AI Stock Analysis Agent",
            page_icon="📊",
            layout="wide",
            # Open Graph metadata
            menu_items={
                'Get Help': None,
                'Report a bug': None,
                'About': """
                # analysis.stocksimulation.kr
                AI Stock Analysis Agent
                """
            }
        )

        # Direct Open Graph tag injection
        og_html = """
        <head>
            <title>analysis.stocksimulation.kr | AI Stock Analysis Agent</title>
            <meta property="og:title" content="analysis.stocksimulation.kr | AI Stock Analysis Agent" />
            <meta property="og:description" content="AI Stock Analysis Agent" />
            <meta property="og:image" content="https://media.istockphoto.com/id/2045262949/ko/%EC%82%AC%EC%A7%84/excited-businessman-raises-hands-and-punches-air-while-celebrating-successful-deal-stock.jpg?s=2048x2048&w=is&k=20&c=XtdmbV6gILRK1ahoMOf0_SFC256rgHyiaID_FeW4ojU=" />
            <meta property="og:url" content="https://analysis.stocksimulation.kr" />
            <meta property="og:type" content="website" />
            <meta property="og:site_name" content="analysis.stocksimulation.kr" />
        </head>
        """
        st.markdown(og_html, unsafe_allow_html=True)

        # Apply custom CSS
        self.apply_custom_styles()

    def apply_custom_styles(self):
        """Custom CSS styling for modern design"""
        st.markdown("""
        <style>
            /* Overall page style */
            .main {
                background-color: #fafafa;
                padding: 1.5rem;
            }
            
            /* Title and header styles */
            h1, h2, h3 {
                font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', sans-serif;
                color: #1E293B;
                font-weight: 700;
            }
            h1 {
                font-size: 2.5rem;
                margin-bottom: 1.5rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid #E2E8F0;
            }
            h2 {
                font-size: 1.8rem;
                margin-top: 2rem;
                margin-bottom: 1rem;
            }
            h3 {
                font-size: 1.3rem;
                margin-top: 1.5rem;
                color: #334155;
            }
            
            /* Card container styles */
            .card {
                background-color: white;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                padding: 1.5rem;
                margin-bottom: 1.5rem;
                border: 1px solid #F1F5F9;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            .card:hover {
                transform: translateY(-3px);
                box-shadow: 0 8px 16px rgba(0, 0, 0, 0.08);
            }
            
            /* Form element styles */
            .stTextInput > div > div > input {
                border-radius: 8px;
                height: 2.8rem;
                border: 1px solid #E2E8F0;
            }
            .stTextInput > div > div > input:focus {
                border-color: #0EA5E9;
                box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.2);
            }
            .stDateInput > div > div > input {
                border-radius: 8px;
            }
            
            /* Button styles */
            .stButton > button {
                background-color: #0EA5E9;
                color: white;
                border-radius: 8px;
                height: 3rem;
                font-weight: 600;
                border: none;
                transition: all 0.2s ease;
            }
            .stButton > button:hover {
                background-color: #0284C7;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(2, 132, 199, 0.2);
            }
            .stButton > button:active {
                transform: translateY(0);
            }
            
            /* Select element styles */
            .stSelectbox > div > div {
                border-radius: 8px;
                border: 1px solid #E2E8F0;
            }
            
            /* Sidebar styles */
            .css-1d391kg, .css-1om1kqc, .css-1n76uvr {
                background-color: #F8FAFC;
                padding: 2rem 1rem;
            }
            
            /* Status message styles */
            .stAlert {
                border-radius: 8px;
                padding: 1rem;
            }
            .success {
                background-color: #ECFDF5;
                color: #065F46;
                border: 1px solid #D1FAE5;
            }
            .error {
                background-color: #FEF2F2;
                color: #991B1B;
                border: 1px solid #FEE2E2;
            }
            .warning {
                background-color: #FFFBEB;
                color: #92400E;
                border: 1px solid #FEF3C7;
            }
            .info {
                background-color: #EFF6FF;
                color: #1E40AF;
                border: 1px solid #DBEAFE;
            }
            
            /* Table styles */
            .dataframe {
                font-family: 'Pretendard', -apple-system, system-ui, sans-serif;
                width: 100%;
                border-collapse: collapse;
            }
            .dataframe th {
                background-color: #F1F5F9;
                padding: 0.75rem 1rem;
                text-align: left;
                font-weight: 600;
                color: #334155;
                border-top: 1px solid #E2E8F0;
                border-bottom: 1px solid #CBD5E1;
            }
            .dataframe td {
                padding: 0.75rem 1rem;
                border-bottom: 1px solid #E2E8F0;
            }
            .dataframe tr:nth-child(even) {
                background-color: #F8FAFC;
            }
            
            /* Download link styles */
            a {
                color: #0EA5E9;
                text-decoration: none;
                font-weight: 500;
                transition: all 0.2s ease;
            }
            a:hover {
                color: #0284C7;
                text-decoration: underline;
            }
            a[download] {
                display: inline-block;
                background-color: #F1F5F9;
                color: #334155;
                font-weight: 600;
                padding: 0.5rem 1rem;
                border-radius: 6px;
                margin-right: 0.5rem;
                border: 1px solid #E2E8F0;
                text-decoration: none;
            }
            a[download]:hover {
                background-color: #E2E8F0;
                text-decoration: none;
            }
            
            /* Progress display styles */
            .stProgress > div > div {
                background-color: #0EA5E9;
            }
            
            /* Markdown body styles */
            .markdown-body {
                font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
                color: #334155;
                line-height: 1.7;
            }
            .markdown-body pre {
                background-color: #F1F5F9;
                border-radius: 8px;
                padding: 1rem;
            }
            .markdown-body table {
                width: 100%;
                border-collapse: collapse;
                margin: 1rem 0;
            }
            .markdown-body table th,
            .markdown-body table td {
                padding: 0.5rem 1rem;
                border: 1px solid #E2E8F0;
            }
            .markdown-body table th {
                background-color: #F1F5F9;
            }
            
            /* Image styles */
            img {
                border-radius: 8px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
            }
            
            /* Header styles */
            .header {
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 1.5rem 0;
                margin-bottom: 2rem;
                text-align: center;
            }
            .logo-container {
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: 0.5rem;
            }
            .logo {
                font-size: 2.5rem;
                margin-right: 0.75rem;
            }
            .app-title {
                font-family: 'Pretendard', -apple-system, system-ui, sans-serif;
                font-size: 2.5rem;
                font-weight: 800;
                color: #0EA5E9;
                letter-spacing: -0.03em;
            }
            .app-description {
                font-size: 1.1rem;
                color: #64748B;
                margin-top: 0.3rem;
                font-weight: 400;
            }
            
            /* Sidebar header */
            .sidebar-header {
                display: flex;
                align-items: center;
                margin-bottom: 1.5rem;
            }
            .sidebar-logo {
                font-size: 1.8rem;
                margin-right: 0.5rem;
            }
            .sidebar-title {
                font-size: 1.3rem;
                font-weight: 700;
                color: #0EA5E9;
            }
            
            /* Status card */
            @keyframes progress-animation {
                0% { width: 0%; }
                20% { width: 20%; }
                40% { width: 40%; }
                60% { width: 60%; }
                80% { width: 80%; }
                100% { width: 40%; }
            }
            
            .status-card {
                display: flex;
                align-items: flex-start;
                padding: 1rem;
                border-radius: 8px;
                margin-bottom: 1rem;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
            }
            .status-icon {
                font-size: 1.5rem;
                margin-right: 1rem;
                margin-top: 0.25rem;
            }
            .status-details {
                flex: 1;
            }
            .status-title {
                font-size: 1.1rem;
                font-weight: 600;
                margin-bottom: 0.3rem;
            }
            .status-info {
                color: #4B5563;
                margin-bottom: 0.5rem;
            }
            .status-card.pending {
                background-color: #FFFBEB;
                border: 1px solid #FEF3C7;
            }
            .status-card.completed {
                background-color: #ECFDF5;
                border: 1px solid #D1FAE5;
            }
            .status-card.failed {
                background-color: #FEF2F2;
                border: 1px solid #FEE2E2;
            }
            .status-progress-container {
                height: 6px;
                background-color: rgba(251, 191, 36, 0.3);
                border-radius: 3px;
                overflow: hidden;
                margin-top: 0.5rem;
            }
            .status-progress-bar {
                height: 100%;
                background-color: #F59E0B;
                width: 40%;
                border-radius: 3px;
                animation: progress-animation 2s infinite alternate;
            }
            
            /* Feature list styles */
            .feature-list {
                list-style-type: none;
                padding: 0;
                margin: 0;
            }
            .feature-list li {
                display: flex;
                align-items: center;
                margin-bottom: 0.8rem;
            }
            .feature-icon {
                font-size: 1.2rem;
                margin-right: 0.7rem;
                width: 24px;
                text-align: center;
            }
            .feature-title {
                font-weight: 600;
                margin-right: 0.5rem;
            }
            
            /* Time display styles */
            .estimate-time {
                display: flex;
                align-items: center;
                margin-bottom: 0.5rem;
            }
            .time-icon {
                font-size: 1.5rem;
                margin-right: 1rem;
            }
            .time-details {
                flex: 1;
            }
            .time-title {
                font-size: 0.9rem;
                color: #64748B;
            }
            .time-value {
                font-size: 1.5rem;
                font-weight: 700;
                color: #0EA5E9;
            }
            .delivery-note {
                color: #64748B;
                font-size: 0.9rem;
                margin-top: 0.3rem;
            }
            
            /* Form card */
            .form-card, .report-card, .filter-card {
                background-color: white;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                padding: 1.5rem;
                margin-bottom: 1.5rem;
                border: 1px solid #F1F5F9;
            }
            
            /* Markdown preview */
            .markdown-preview {
                padding: 1rem;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                background-color: #F8FAFC;
                max-height: 600px;
                overflow-y: auto;
            }
        </style>
        """, unsafe_allow_html=True)

    def add_app_header(self):
        """Add app header and branding"""
        st.markdown("""
        <div class="header">
            <div class="logo-container">
                <div class="logo">📊</div>
                <div class="app-title">analysis.stocksimulation.kr</div>
            </div>
            <div class="app-description">
                AI Stock Analysis Agent
            </div>
        </div>
        """, unsafe_allow_html=True)

    def create_card(self, title, content, icon=None):
        """Create card component"""
        icon_html = f'<div class="card-icon">{icon}</div>' if icon else ''
        
        st.markdown(f"""
        <div class="card">
            <div class="card-header">
                {icon_html}
                <div class="card-title">{title}</div>
            </div>
            <div class="card-content">
                {content}
            </div>
        </div>
        <style>
            .card-header {{
                display: flex;
                align-items: center;
                margin-bottom: 1rem;
            }}
            .card-icon {{
                font-size: 1.5rem;
                margin-right: 0.8rem;
                color: #0EA5E9;
            }}
            .card-title {{
                font-size: 1.2rem;
                font-weight: 600;
                color: #1E293B;
            }}
            .card-content {{
                color: #334155;
                line-height: 1.6;
            }}
        </style>
        """, unsafe_allow_html=True)

    def initialize_session_state(self):
        """Initialize session state"""
        if 'requests' not in st.session_state:
            st.session_state.requests = {}
        if 'processing' not in st.session_state:
            st.session_state.processing = False

    def start_background_worker(self):
        """Start background worker"""
        def worker():
            while True:
                request = analysis_queue.get()
                try:
                    self.process_analysis_request(request)
                except Exception as e:
                    print(f"Error processing request {request.id}: {str(e)}")
                finally:
                    analysis_queue.task_done()

        for _ in range(5):  # Start 5 worker threads
            Thread(target=worker, daemon=True).start()

    def process_analysis_request(self, request: AnalysisRequest):
        """Process analysis request"""
        try:
            # Check for cached report
            is_cached, cached_content, cached_file = self.get_cached_report(
                request.stock_code, request.reference_date
            )

            if is_cached:
                # Send email immediately if cached report exists
                send_email(request.email, cached_content)
                request.result = f"Cached analysis report has been sent via email. (File: {cached_file.name})"
            else:
                # Run analysis as separate process
                import subprocess
                import tempfile
                import json

                # Project root directory and streamlit directory paths
                project_root = str(Path(__file__).parent.parent.parent.absolute())
                streamlit_dir = str(Path(__file__).parent.absolute())

                # Save request info to temporary file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    request_info = {
                        'stock_code': request.stock_code,
                        'company_name': request.company_name,
                        'reference_date': request.reference_date,
                        'output_file': f"reports/{request.stock_code}_{request.company_name}_{request.reference_date}_gpt5.4-mini.md",
                        'email': request.email
                    }
                    json.dump(request_info, f)
                    request_file = f.name

                # Run separate process
                subprocess.Popen([
                    "python", "-c",
                    f'''
import asyncio, json, os, sys

# Set Python path
project_root = "{project_root}"
streamlit_dir = "{streamlit_dir}"
sys.path.insert(0, project_root)
sys.path.insert(0, streamlit_dir)

# Change working directory
os.chdir(project_root)

print(f"Working directory: {{os.getcwd()}}")
print(f"Python path: {{sys.path[:3]}}")

try:
    from cores.main import analyze_stock
    print("Successfully imported analyze_stock")
except ImportError as e:
    print(f"Failed to import analyze_stock: {{e}}")
    exit(1)

try:
    from email_sender import send_email
    print("Successfully imported send_email")
except ImportError as e:
    print(f"Failed to import send_email: {{e}}")
    exit(1)

# Load request info
with open("{request_file}", "r") as f:
    info = json.load(f)

# Run analysis
async def run():
    try:
        print(f"Starting analysis for {{info['company_name']}} ({{info['stock_code']}})")
        report = await analyze_stock(
            company_code=info["stock_code"],
            company_name=info["company_name"],
            reference_date=info["reference_date"]
        )
        
        # Save results
        with open(info["output_file"], "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report saved to {{info['output_file']}}")
        
        # Send email 
        if send_email(info["email"], report):
            print(f"Email sent successfully to {{info['email']}}")
        else:
            print(f"Failed to send email to {{info['email']}}")
        
        # Delete temporary file
        os.remove("{request_file}")
        print("Analysis completed successfully")
        
    except Exception as e:
        print(f"Error during analysis: {{e}}")
        import traceback
        traceback.print_exc()

asyncio.run(run())
'''
                ], cwd=project_root)

                request.result = f"Analysis has started. Results will be sent via email upon completion."

            request.status = "completed"

        except Exception as e:
            request.status = "failed"
            request.result = f"An error occurred during analysis: {str(e)}"

    @staticmethod
    def get_cached_report(stock_code: str, reference_date: str) -> tuple[bool, str, Path | None]:
        """Search for cached report"""
        report_pattern = f"{stock_code}_*_{reference_date}*.md"
        matching_files = list(REPORTS_DIR.glob(report_pattern))

        if matching_files:
            latest_file = max(matching_files, key=lambda p: p.stat().st_mtime)
            with open(latest_file, "r", encoding="utf-8") as f:
                return True, f.read(), latest_file
        return False, "", None

    @staticmethod
    def save_report(stock_code: str, company_name: str, reference_date: str, content: str) -> Path:
        """Save report to file"""
        filename = f"{stock_code}_{company_name}_{reference_date}_gpt4o.md"
        filepath = REPORTS_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def submit_analysis(self, stock_code: str, company_name: str, email: str, reference_date: str) -> str:
        """Submit analysis request"""
        request = AnalysisRequest(stock_code, company_name, email, reference_date)
        st.session_state.requests[request.id] = request
        analysis_queue.put(request)
        return request.id

    def render_modern_analysis_form(self):
        """Modern design analysis request form"""
        # Add custom header
        self.add_app_header()

        # App description card
        st.markdown("### 🤖 AI Stock Analysis Agent Service")
        st.markdown("This service utilizes AI to conduct in-depth stock analysis and automatically generates professional-grade investment analysis reports. Enter company information and your email, and the results will be sent to you upon completion.")

        # Two-column layout
        col1, col2 = st.columns([2, 1])

        with col1:
            # Analysis request card
            st.markdown("## Analysis Request")

            with st.form("analysis_form"):
                form_col1, form_col2 = st.columns(2)

                with form_col1:
                    company_name = st.text_input("Company Name", placeholder="Example: Samsung Electronics")
                    email = st.text_input("Email Address", placeholder="Email to receive results")

                with form_col2:
                    stock_code = st.text_input("Stock Code", placeholder="Example: 005930 (6 digits)")
                    today = datetime.now().date()
                    analysis_date = st.date_input(
                        "Analysis Reference Date",
                        value=today,
                        max_value=today
                    )

                # FAQ toggle
                with st.expander("📌 Frequently Asked Questions"):
                    st.markdown("""
                    **Q: How long does the analysis take?**  
                    A: Typically, it takes 5-10 minutes.
                    
                    **Q: What information is included?**  
                    A: Stock price analysis, financial statement analysis, competitor comparison, investment indicators, news analysis, etc.
                    
                    **Q: How do I receive the results?**  
                    A: Results are sent to the email you provided and can also be viewed in the 'View Reports' menu on this site.
                    """)

                # Styled submit button
                submit_col1, submit_col2, submit_col3 = st.columns([1, 2, 1])
                with submit_col2:
                    submitted = st.form_submit_button("Start Analysis", use_container_width=True)

            # Form submission handling
            if submitted:
                if not self.validate_inputs(company_name, stock_code, email):
                    return

                reference_date = analysis_date.strftime("%Y%m%d")
                request_id = self.submit_analysis(stock_code, company_name, email, reference_date)
                st.success("Analysis has been requested. Results will be sent to your email upon completion. You can also view them later in the 'View Reports' menu on this website.")

        with col2:
            # Analysis info card
            st.markdown("### ✨ Analysis Features")
            features = [
                {"icon": "📊", "title": "Technical Analysis", "desc": "Stock price patterns and momentum analysis"},
                {"icon": "💰", "title": "Financial Analysis", "desc": "Comprehensive financial statement analysis"},
                {"icon": "🏢", "title": "Competitor Comparison", "desc": "Relative position evaluation within the industry"},
                {"icon": "📈", "title": "Investment Indicators", "desc": "PER, PBR, ROE and other key investment metrics"},
                {"icon": "📰", "title": "News Analysis", "desc": "Latest news and market reaction analysis"}
            ]

            for feature in features:
                st.markdown(f"{feature['icon']} **{feature['title']}** - {feature['desc']}")

            # Estimated completion time
            st.markdown("### Estimated Analysis Time")
            st.markdown("⏱️ **5-10 minutes**")
            st.markdown("Results will be sent via email upon completion")

        # Analysis status section
        if st.session_state.requests:
            self.render_request_status()

    def render_request_status(self):
        """Method to display request status"""
        st.markdown("## 📋 In-Progress Analysis")

        # Categorize requests by status
        pending_requests = []
        completed_requests = []
        failed_requests = []

        for request_id, request in st.session_state.requests.items():
            if request.status == "pending":
                pending_requests.append(request)
            elif request.status == "completed":
                completed_requests.append(request)
            elif request.status == "failed":
                failed_requests.append(request)

        # Display pending requests
        if pending_requests:
            for request in pending_requests:
                st.info(f"⏳ {request.company_name} ({request.stock_code}) - Analysis in progress... (approximately 5-10 minutes)")

        # Display completed requests
        if completed_requests:
            for request in completed_requests:
                st.success(f"✅ {request.company_name} ({request.stock_code}) - {request.result}")

        # Display failed requests
        if failed_requests:
            for request in failed_requests:
                st.error(f"❌ {request.company_name} ({request.stock_code}) - {request.result}")

    def render_modern_report_viewer(self):
        """Modern design report viewer"""
        # Add custom header
        self.add_app_header()
        
        # Report viewer introduction
        intro_content = """
        <p>Search and view previously generated analysis reports. 
        Search by stock code or select from the list to view reports.</p>
        """
        self.create_card("Report Viewer", intro_content, "📑")
        
        # Search and filter area
        col1, col2 = st.columns([1, 3])
        
        with col1:
            st.markdown('<div class="filter-card">', unsafe_allow_html=True)
            st.subheader("Search Reports")
            search_code = st.text_input("Search by Stock Code", placeholder="Example: 005930")
            
            # Get list of saved reports
            reports = list(REPORTS_DIR.glob("*.md"))
            
            if search_code:
                reports = [r for r in reports if search_code in r.stem]
            
            if not reports:
                st.warning("No saved reports found.")
                st.markdown('</div>', unsafe_allow_html=True)
                return
            
            # Categorize reports
            st.markdown("### Report Categories")
            report_dates = {}
            
            for report in reports:
                # Categorize by file modification date
                mod_date = datetime.fromtimestamp(report.stat().st_mtime).strftime('%Y-%m-%d')
                if mod_date not in report_dates:
                    report_dates[mod_date] = []
                report_dates[mod_date].append(report)
            
            # Display report count by date
            for date, date_reports in sorted(report_dates.items(), reverse=True):
                st.markdown(f"**{date}** ({len(date_reports)} reports)")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            # Report selection and display area
            st.markdown('<div class="report-card">', unsafe_allow_html=True)
            st.subheader("Report List")
            
            # Sort reports (newest first)
            reports.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Modern UI for report selection
            report_options = [f"{r.stem} ({datetime.fromtimestamp(r.stat().st_mtime).strftime('%Y-%m-%d %H:%M')})" for r in reports]
            report_dict = dict(zip(report_options, reports))
            
            selected_report_name = st.selectbox(
                "Select Report",
                options=report_options
            )
            
            if selected_report_name:
                selected_report = report_dict[selected_report_name]
                
                # Display report metadata
                report_meta_col1, report_meta_col2 = st.columns(2)
                with report_meta_col1:
                    st.markdown(f"**Created:** {datetime.fromtimestamp(selected_report.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
                with report_meta_col2:
                    st.markdown(f"**File Size:** {selected_report.stat().st_size / 1024:.1f} KB")
                
                # Download button area
                st.markdown("### Download Options")
                download_col1, download_col2 = st.columns(2)
                with download_col1:
                    st.markdown(self.get_download_link(selected_report, 'md'), unsafe_allow_html=True)
                with download_col2:
                    st.markdown(self.get_download_link(selected_report, 'html'), unsafe_allow_html=True)
                
                # Report preview
                st.markdown("### Report Preview")
                
                with open(selected_report, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Display with styled markdown
                st.markdown('<div class="markdown-preview">', unsafe_allow_html=True)
                st.markdown(content)
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)

    def validate_inputs(self, company_name: str, stock_code: str, email: str) -> bool:
        """Validate input values"""
        if not company_name:
            st.error("Please enter the company name.")
            return False

        if not self.is_valid_stock_code(stock_code):
            st.error("Please enter a valid stock code (6-digit number).")
            return False

        if not self.is_valid_email(email):
            st.error("Please enter a valid email address.")
            return False

        return True

    @staticmethod
    def is_valid_stock_code(code: str) -> bool:
        return bool(re.match(r'^\d{6}$', code))

    @staticmethod
    def is_valid_email(email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def get_download_link(file_path: Path, file_format: str) -> str:
        """Generate download link"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()

        if file_format == 'html':
            # Convert markdown to HTML
            html_content = markdown.markdown(
                data,
                extensions=['markdown.extensions.fenced_code', 'markdown.extensions.tables']
            )
            b64 = base64.b64encode(html_content.encode()).decode()
            extension = 'html'
        else:
            b64 = base64.b64encode(data.encode()).decode()
            extension = 'md'

        filename = f"{file_path.stem}.{extension}"
        return f'<a href="data:file/{extension};base64,{b64}" download="{filename}">💾 Download as {extension.upper()}</a>'

    def main(self):
        """Main application execution"""
        # Improved sidebar design
        st.sidebar.markdown("""
        <div class="sidebar-header">
            <div class="sidebar-logo">📊</div>
            <div class="sidebar-title">analysis.stocksimulation.kr</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.sidebar.title("Menu")
        
        # Modern sidebar menu
        menu_options = {
            "Analysis Request": "📝",
            "View Reports": "📚"
        }
        
        menu = st.sidebar.radio(
            "Select",
            list(menu_options.keys()),
            format_func=lambda x: f"{menu_options[x]} {x}"
        )
        
        # App version and social links
        st.sidebar.markdown("---")
        st.sidebar.markdown("#### Service Information")
        st.sidebar.markdown("Version: v1.0.2")
        st.sidebar.markdown("© 2025 https://analysis.stocksimulation.kr")
        
        # Render main content
        if menu == "Analysis Request":
            self.render_modern_analysis_form()
        else:
            self.render_modern_report_viewer()

if __name__ == "__main__":
    app = ModernStockAnalysisApp()
    app.main()
