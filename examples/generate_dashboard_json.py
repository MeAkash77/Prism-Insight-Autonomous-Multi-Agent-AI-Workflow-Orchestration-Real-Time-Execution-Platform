#!/usr/bin/env python3
"""
JSON Data Generation Script for Stock Portfolio Dashboard
Run periodically with Cron (e.g., */5 * * * * - every 5 minutes)

Usage:
    python generate_dashboard_json.py

Output:
    ./dashboard/public/dashboard_data.json - All data for dashboard
"""
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

import sqlite3
import json
import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import logging
import os

# Logging setup (configure before other imports)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Path setup (configure before importing other modules)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
TRADING_DIR = PROJECT_ROOT / "trading"
sys.path.insert(0, str(SCRIPT_DIR))  # Add examples/ folder for translation_utils
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TRADING_DIR))

# krx_data_client import for market index data
try:
    from krx_data_client import get_index_ohlcv_by_date

    # pykrx compatibility wrapper
    class stock:
        @staticmethod
        def get_index_ohlcv_by_date(fromdate, todate, ticker):
            return get_index_ohlcv_by_date(fromdate, todate, ticker)

    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False
    logger.warning("krx_data_client package not installed. Cannot fetch market index data.")

# Import translation utility (after path setup)
try:
    from translation_utils import DashboardTranslator
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False
    logger.warning("Translation utility not found. English translation disabled.")

# Load configuration file
CONFIG_FILE = TRADING_DIR / "config" / "kis_devlp.yaml"
try:
    with open(CONFIG_FILE, encoding="UTF-8") as f:
        _cfg = yaml.load(f, Loader=yaml.FullLoader)
except FileNotFoundError:
    _cfg = {"default_mode": "demo"}
    logger.warning(f"Configuration file not found: {CONFIG_FILE}. Using default mode (demo).")

# Import Korea Investment & Securities API module
try:
    from trading.domestic_stock_trading import DomesticStockTrading
    KIS_AVAILABLE = True
except ImportError:
    KIS_AVAILABLE = False
    logger.warning("Korea Investment & Securities API module not found. Cannot fetch live trading data.")


class DashboardDataGenerator:
    def __init__(self, db_path: str = None, output_path: str = None, trading_mode: str = None, enable_translation: bool = True):
        # db_path default: stock_tracking_db.sqlite in project root
        if db_path is None:
            db_path = str(PROJECT_ROOT / "stock_tracking_db.sqlite")
        
        # output_path default: examples/dashboard/public/dashboard_data.json
        if output_path is None:
            output_path = str(SCRIPT_DIR / "dashboard" / "public" / "dashboard_data.json")
        
        self.db_path = db_path
        self.output_path = output_path
        self.trading_mode = trading_mode if trading_mode is not None else _cfg.get("default_mode", "demo")
        self.enable_translation = enable_translation and TRANSLATION_AVAILABLE
        
        # Initialize translator
        if self.enable_translation:
            try:
                self.translator = DashboardTranslator(model="gpt-5-nano")
                logger.info("Translation enabled.")
            except Exception as e:
                self.enable_translation = False
                logger.error(f"Translator initialization failed: {str(e)}")
        else:
            logger.info("Translation disabled.")
        
    def connect_db(self):
        """Database connection"""
        return sqlite3.connect(self.db_path)
    
    def get_kis_trading_data(self) -> Dict[str, Any]:
        """Fetch live trading data from Korea Investment & Securities API"""
        if not KIS_AVAILABLE:
            logger.warning("Korea Investment & Securities API is not available.")
            return {"portfolio": [], "account_summary": {}}
        
        try:
            logger.info(f"Fetching Korea Investment & Securities data... (Mode: {self.trading_mode})")
            trader = DomesticStockTrading(mode=self.trading_mode)
            
            # Fetch portfolio data
            portfolio = trader.get_portfolio()
            logger.info(f"Portfolio fetch completed: {len(portfolio)} stocks")
            
            # Fetch account summary data
            account_summary = trader.get_account_summary()
            logger.info("Account summary fetch completed")
            
            # Transform data (to match dashboard format)
            formatted_portfolio = []
            for stock in portfolio:
                formatted_stock = {
                    "ticker": stock.get("stock_code", ""),
                    "name": stock.get("stock_name", ""),
                    "quantity": stock.get("quantity", 0),
                    "avg_price": stock.get("avg_price", 0),
                    "current_price": stock.get("current_price", 0),
                    "value": stock.get("eval_amount", 0),
                    "profit": stock.get("profit_amount", 0),
                    "profit_rate": stock.get("profit_rate", 0),
                    "sector": "Live Trading",  # Default if sector info is missing
                    "weight": 0  # Calculated later
                }
                formatted_portfolio.append(formatted_stock)
            
            # Calculate portfolio weight
            total_value = sum(s["value"] for s in formatted_portfolio)
            if total_value > 0:
                for stock in formatted_portfolio:
                    stock["weight"] = (stock["value"] / total_value) * 100
            
            return {
                "portfolio": formatted_portfolio,
                "account_summary": account_summary
            }
            
        except Exception as e:
            logger.error(f"Error fetching Korea Investment & Securities data: {str(e)}")
            return {"portfolio": [], "account_summary": {}}
        
    def connect_db(self):
        """Database connection"""
        return sqlite3.connect(self.db_path)
    
    def parse_json_field(self, json_str: str) -> Dict:
        """Parse JSON string (with error handling)"""
        if not json_str:
            return {}
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed: {str(e)}")
            return {}

    def normalize_lessons(self, lessons_data) -> List[Dict]:
        """Normalize L1/L2/L3 lessons data into a consistent structure

        L1 (detailed): [{condition, action, reason, priority}] - Complete object array
        L2 (compressed): ["lesson string 1", ...] or [{action}] - May lack priority field
        L3 (minimal): Even simpler form

        Unify all forms into {condition, action, reason, priority} structure
        """
        if not lessons_data:
            return []

        normalized = []
        for item in lessons_data:
            if isinstance(item, str):
                # L2 string lesson: "lesson content" → {action: "lesson content", priority: "medium"}
                normalized.append({
                    'condition': '',
                    'action': item,
                    'reason': '',
                    'priority': 'medium'
                })
            elif isinstance(item, dict):
                # L1 or partial object: fill missing fields with defaults
                normalized.append({
                    'condition': item.get('condition', ''),
                    'action': item.get('action', str(item)),
                    'reason': item.get('reason', ''),
                    'priority': item.get('priority', 'medium')
                })
            else:
                # Other types: convert to string
                normalized.append({
                    'condition': '',
                    'action': str(item),
                    'reason': '',
                    'priority': 'medium'
                })
        return normalized
    
    def dict_from_row(self, row, cursor) -> Dict:
        """Convert SQLite Row to Dictionary"""
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
    
    def get_stock_holdings(self, conn) -> List[Dict]:
        """Fetch current stock holdings data"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ticker, company_name, buy_price, buy_date, current_price, 
                   last_updated, scenario, target_price, stop_loss
            FROM stock_holdings
            ORDER BY buy_date DESC
        """)
        
        holdings = []
        for row in cursor.fetchall():
            holding = self.dict_from_row(row, cursor)
            
            # Parse scenario JSON
            holding['scenario'] = self.parse_json_field(holding.get('scenario', ''))
            
            # Calculate profit rate
            buy_price = holding.get('buy_price', 0)
            current_price = holding.get('current_price', 0)
            if buy_price > 0:
                holding['profit_rate'] = ((current_price - buy_price) / buy_price) * 100
            else:
                holding['profit_rate'] = 0
            
            # Calculate holding period
            buy_date = holding.get('buy_date', '')
            if buy_date:
                try:
                    buy_dt = datetime.strptime(buy_date, "%Y-%m-%d %H:%M:%S")
                    holding['holding_days'] = (datetime.now() - buy_dt).days
                except:
                    holding['holding_days'] = 0
            else:
                holding['holding_days'] = 0
            
            holdings.append(holding)
        
        return holdings
    
    def get_trading_history(self, conn) -> List[Dict]:
        """Fetch trading history data"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ticker, company_name, buy_price, buy_date, sell_price, 
                   sell_date, profit_rate, holding_days, scenario
            FROM trading_history
            ORDER BY sell_date DESC
        """)
        
        history = []
        for row in cursor.fetchall():
            trade = self.dict_from_row(row, cursor)
            
            # Parse scenario JSON
            trade['scenario'] = self.parse_json_field(trade.get('scenario', ''))
            
            history.append(trade)
        
        return history
    
    def get_watchlist_history(self, conn) -> List[Dict]:
        """Fetch non-entry stocks data"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ticker, company_name, current_price, analyzed_date, 
                   buy_score, min_score, decision, skip_reason, target_price, 
                   stop_loss, investment_period, sector, scenario, 
                   portfolio_analysis, valuation_analysis, sector_outlook, 
                   market_condition, rationale
            FROM watchlist_history
            ORDER BY analyzed_date DESC
        """)
        
        watchlist = []
        for row in cursor.fetchall():
            item = self.dict_from_row(row, cursor)
            
            # Parse scenario JSON
            item['scenario'] = self.parse_json_field(item.get('scenario', ''))
            
            watchlist.append(item)
        
        return watchlist
    
    def get_market_condition(self, conn) -> List[Dict]:
        """Fetch market condition data - collect from Season2 start (2025-09-29) using pykrx"""
        # Season2 start date
        SEASON2_START_DATE = "20250929"

        if not PYKRX_AVAILABLE:
            logger.warning("pykrx is not available. Fetching data from DB.")
            return self._get_market_condition_from_db(conn)

        try:
            # Today's date
            today = datetime.now().strftime("%Y%m%d")

            logger.info(f"Fetching market index data with pykrx... ({SEASON2_START_DATE} ~ {today})")

            # Fetch KOSPI index data (ticker: 1001)
            kospi_df = stock.get_index_ohlcv_by_date(SEASON2_START_DATE, today, "1001")

            # Fetch KOSDAQ index data (ticker: 2001)
            kosdaq_df = stock.get_index_ohlcv_by_date(SEASON2_START_DATE, today, "2001")

            if kospi_df.empty or kosdaq_df.empty:
                logger.warning("Failed to fetch index data from pykrx. Falling back to DB.")
                return self._get_market_condition_from_db(conn)

            # Merge data
            market_data = []

            for date_idx in kospi_df.index:
                date_str = date_idx.strftime("%Y-%m-%d")

                kospi_close = kospi_df.loc[date_idx, 'Close']

                # Use KOSDAQ only if same date exists
                if date_idx in kosdaq_df.index:
                    kosdaq_close = kosdaq_df.loc[date_idx, 'Close']
                else:
                    kosdaq_close = 0

                market_data.append({
                    'date': date_str,
                    'kospi_index': float(kospi_close),
                    'kosdaq_index': float(kosdaq_close),
                    'condition': 0,  # Default value
                    'volatility': 0  # Default value
                })

            # Sort by date ascending (for chart use)
            market_data.sort(key=lambda x: x['date'])

            logger.info(f"Successfully collected {len(market_data)} days of market index data")
            return market_data

        except Exception as e:
            logger.error(f"Error fetching market index data from pykrx: {str(e)}")
            return self._get_market_condition_from_db(conn)

    def _get_market_condition_from_db(self, conn) -> List[Dict]:
        """Fetch market condition data from DB (fallback)"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, kospi_index, kosdaq_index, condition, volatility
            FROM market_condition
            ORDER BY date ASC
        """)

        market_data = []
        for row in cursor.fetchall():
            market = self.dict_from_row(row, cursor)
            market_data.append(market)

        return market_data
    
    def get_holding_decisions(self, conn) -> List[Dict]:
        """Fetch sell decision data for holdings (today only, including company name)"""
        try:
            cursor = conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")

            # LEFT JOIN with stock_holdings to get company_name
            cursor.execute("""
                SELECT hd.id, hd.ticker, hd.decision_date, hd.decision_time, hd.current_price,
                       hd.should_sell, hd.sell_reason, hd.confidence, hd.technical_trend,
                       hd.volume_analysis, hd.market_condition_impact, hd.time_factor,
                       hd.portfolio_adjustment_needed, hd.adjustment_reason,
                       hd.new_target_price, hd.new_stop_loss, hd.adjustment_urgency,
                       hd.full_json_data, hd.created_at,
                       sh.company_name
                FROM holding_decisions hd
                LEFT JOIN stock_holdings sh ON hd.ticker = sh.ticker
                WHERE hd.decision_date = ?
                ORDER BY hd.created_at DESC
            """, (today,))

            decisions = []
            for row in cursor.fetchall():
                decision = self.dict_from_row(row, cursor)

                # Parse full_json_data
                decision['full_json_data'] = self.parse_json_field(decision.get('full_json_data', ''))

                decisions.append(decision)

            return decisions
        except Exception as e:
            logger.warning(f"Failed to query holding_decisions table (table may not exist): {str(e)}")
            return []
    
    def calculate_portfolio_summary(self, holdings: List[Dict]) -> Dict:
        """Calculate portfolio summary statistics"""
        if not holdings:
            return {
                'total_stocks': 0,
                'total_profit': 0,
                'avg_profit_rate': 0,
                'slot_usage': '0/10',
                'slot_percentage': 0
            }
        
        total_profit = sum(h.get('profit_rate', 0) for h in holdings)
        avg_profit_rate = total_profit / len(holdings) if holdings else 0
        
        # Sector distribution
        sector_distribution = {}
        for h in holdings:
            scenario = h.get('scenario', {})
            sector = scenario.get('sector', 'Other')
            sector_distribution[sector] = sector_distribution.get(sector, 0) + 1
        
        # Investment period distribution
        period_distribution = {}
        for h in holdings:
            scenario = h.get('scenario', {})
            period = scenario.get('investment_period', 'Short-term')
            period_distribution[period] = period_distribution.get(period, 0) + 1
        
        return {
            'total_stocks': len(holdings),
            'total_profit': total_profit,
            'avg_profit_rate': avg_profit_rate,
            'slot_usage': f'{len(holdings)}/10',
            'slot_percentage': (len(holdings) / 10) * 100,
            'sector_distribution': sector_distribution,
            'period_distribution': period_distribution
        }
    
    def calculate_trading_summary(self, history: List[Dict]) -> Dict:
        """Calculate trading history summary statistics"""
        if not history:
            return {
                'total_trades': 0,
                'win_count': 0,
                'loss_count': 0,
                'win_rate': 0,
                'avg_profit_rate': 0,
                'avg_holding_days': 0
            }
        
        win_count = sum(1 for h in history if h.get('profit_rate', 0) > 0)
        loss_count = len(history) - win_count
        win_rate = (win_count / len(history)) * 100 if history else 0
        
        avg_profit_rate = sum(h.get('profit_rate', 0) for h in history) / len(history)
        avg_holding_days = sum(h.get('holding_days', 0) for h in history) / len(history)
        
        return {
            'total_trades': len(history),
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': win_rate,
            'avg_profit_rate': avg_profit_rate,
            'avg_holding_days': avg_holding_days
        }
    
    def get_ai_decision_summary(self, decisions: List[Dict]) -> Dict:
        """AI decision summary statistics"""
        if not decisions:
            return {
                'total_decisions': 0,
                'sell_signals': 0,
                'hold_signals': 0,
                'adjustment_needed': 0,
                'avg_confidence': 0
            }
        
        sell_signals = sum(1 for d in decisions if d.get('should_sell', False))
        hold_signals = len(decisions) - sell_signals
        adjustment_needed = sum(1 for d in decisions if d.get('portfolio_adjustment_needed', False))
        
        avg_confidence = sum(d.get('confidence', 0) for d in decisions) / len(decisions) if decisions else 0
        
        return {
            'total_decisions': len(decisions),
            'sell_signals': sell_signals,
            'hold_signals': hold_signals,
            'adjustment_needed': adjustment_needed,
            'avg_confidence': avg_confidence
        }
    
    def calculate_real_trading_summary(self, real_portfolio: List[Dict], account_summary: Dict) -> Dict:
        """Calculate real trading summary statistics (including cash information)"""
        if not real_portfolio and not account_summary:
            return {
                'total_stocks': 0,
                'total_eval_amount': 0,
                'total_profit_amount': 0,
                'total_profit_rate': 0,
                'deposit': 0,
                'total_cash': 0,
                'available_amount': 0
            }

        # Use total_cash (including D+2), fallback to deposit if not available
        total_cash = account_summary.get('total_cash', account_summary.get('deposit', 0))

        return {
            'total_stocks': len(real_portfolio),
            'total_eval_amount': account_summary.get('total_eval_amount', 0),
            'total_profit_amount': account_summary.get('total_profit_amount', 0),
            'total_profit_rate': account_summary.get('total_profit_rate', 0),
            'deposit': account_summary.get('deposit', 0),  # Deposit (D+0)
            'total_cash': total_cash,  # Total cash (including D+2)
            'available_amount': account_summary.get('available_amount', 0)
        }

    def calculate_cumulative_realized_profit(self, trading_history: List[Dict], market_data: List[Dict]) -> List[Dict]:
        """
        Calculate daily cumulative realized profit for Prism simulator

        - Calculates profit rate based on 10 slots (sum of sold stocks' profit_rate / 10)
        - Returns cumulative return for each market trading day
        """
        SEASON2_START_DATE = "2025-09-29"

        # Sort trading history by sell_date
        sorted_trades = sorted(
            [t for t in trading_history if t.get('sell_date')],
            key=lambda x: x.get('sell_date', '')
        )

        # Calculate cumulative profit by date
        cumulative_profit = 0.0
        cumulative_by_date = {}

        for trade in sorted_trades:
            sell_date = trade.get('sell_date', '')
            if sell_date:
                # Extract only date if datetime format
                if ' ' in sell_date:
                    sell_date = sell_date.split(' ')[0]

                profit_rate = trade.get('profit_rate', 0)
                cumulative_profit += profit_rate
                cumulative_by_date[sell_date] = cumulative_profit

        # Generate Prism return data for each date in market data
        result = []
        last_cumulative = 0.0

        for market_item in market_data:
            date = market_item.get('date', '')

            if date < SEASON2_START_DATE:
                continue

            # Find cumulative realized profit up to this date
            for trade_date, cum_profit in cumulative_by_date.items():
                if trade_date <= date:
                    last_cumulative = cum_profit

            # Calculate Prism return based on 10 slots
            prism_return = last_cumulative / 10

            result.append({
                'date': date,
                'cumulative_realized_profit': last_cumulative,
                'prism_simulator_return': prism_return
            })

        return result
    
    def get_operating_costs(self) -> Dict:
        """Return project operating cost data"""
        # Operating costs as of January 2026
        return {
            'server_hosting': 31.68,
            'openai_api': 234.15,
            'anthropic_api': 11.4,
            'firecrawl_api': 19.0,
            'perplexity_api': 16.5,
            'month': '2026-01'
        }
    
    def get_trading_insights(self, conn) -> Dict:
        """Fetch trading insights data (trading_journal, trading_principles, trading_intuitions)"""
        try:
            cursor = conn.cursor()

            # 1. Query trading_principles
            cursor.execute("""
                SELECT id, scope, scope_context, condition, action, reason,
                       priority, confidence, supporting_trades, is_active,
                       created_at, last_validated_at
                FROM trading_principles
                WHERE is_active = 1
                ORDER BY
                    CASE priority
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        WHEN 'low' THEN 3
                    END,
                    confidence DESC
            """)

            principles = []
            for row in cursor.fetchall():
                principle = self.dict_from_row(row, cursor)
                principle['is_active'] = bool(principle.get('is_active', 0))
                principles.append(principle)

            logger.info(f"Trading principles fetch completed: {len(principles)} items")

            # 2. Query trading_journal
            cursor.execute("""
                SELECT id, ticker, company_name, trade_date, trade_type,
                       buy_price, sell_price, profit_rate, holding_days,
                       one_line_summary, situation_analysis, judgment_evaluation,
                       lessons, pattern_tags, compression_layer
                FROM trading_journal
                ORDER BY trade_date DESC
                LIMIT 50
            """)

            journal_entries = []
            for row in cursor.fetchall():
                entry = self.dict_from_row(row, cursor)
                # Parse JSON fields and normalize lessons (L1/L2/L3 compatible)
                raw_lessons = self.parse_json_field(entry.get('lessons', '[]'))
                entry['lessons'] = self.normalize_lessons(raw_lessons)
                entry['pattern_tags'] = self.parse_json_field(entry.get('pattern_tags', '[]'))
                journal_entries.append(entry)

            logger.info(f"Trading journal fetch completed: {len(journal_entries)} entries")

            # 3. Query trading_intuitions
            cursor.execute("""
                SELECT id, category, condition, insight, confidence,
                       success_rate, supporting_trades, is_active, subcategory
                FROM trading_intuitions
                WHERE is_active = 1
                ORDER BY confidence DESC
            """)

            intuitions = []
            for row in cursor.fetchall():
                intuition = self.dict_from_row(row, cursor)
                intuition['is_active'] = bool(intuition.get('is_active', 0))
                intuitions.append(intuition)

            logger.info(f"Trading intuitions fetch completed: {len(intuitions)} items")

            # 4. Calculate summary statistics
            high_priority_count = sum(1 for p in principles if p.get('priority') == 'high')
            avg_profit_rate = sum(e.get('profit_rate', 0) for e in journal_entries) / len(journal_entries) if journal_entries else 0
            avg_confidence = sum(p.get('confidence', 0) for p in principles) / len(principles) if principles else 0

            summary = {
                'total_principles': len(principles),
                'active_principles': len(principles),  # Already filtered by is_active=1
                'high_priority_count': high_priority_count,
                'total_journal_entries': len(journal_entries),
                'avg_profit_rate': avg_profit_rate,
                'total_intuitions': len(intuitions),
                'avg_confidence': avg_confidence
            }

            return {
                'summary': summary,
                'principles': principles,
                'journal_entries': journal_entries,
                'intuitions': intuitions
            }

        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                logger.warning(f"Trading insights table does not exist: {str(e)}")
                return {
                    'summary': {
                        'total_principles': 0,
                        'active_principles': 0,
                        'high_priority_count': 0,
                        'total_journal_entries': 0,
                        'avg_profit_rate': 0,
                        'total_intuitions': 0,
                        'avg_confidence': 0
                    },
                    'principles': [],
                    'journal_entries': [],
                    'intuitions': []
                }
            else:
                raise
        except Exception as e:
            logger.error(f"Error collecting trading insights data: {str(e)}")
            return {
                'summary': {
                    'total_principles': 0,
                    'active_principles': 0,
                    'high_priority_count': 0,
                    'total_journal_entries': 0,
                    'avg_profit_rate': 0,
                    'total_intuitions': 0,
                    'avg_confidence': 0
                },
                'principles': [],
                'journal_entries': [],
                'intuitions': []
            }

    def get_performance_analysis(self, conn) -> Dict:
        """Fetch trigger performance analysis data (analysis_performance_tracker table)"""
        try:
            cursor = conn.cursor()

            # 1. Overall status query
            cursor.execute("""
                SELECT
                    tracking_status,
                    COUNT(*) as count
                FROM analysis_performance_tracker
                GROUP BY tracking_status
            """)
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT
                    was_traded,
                    COUNT(*) as count
                FROM analysis_performance_tracker
                GROUP BY was_traded
            """)
            traded_counts = {}
            for row in cursor.fetchall():
                key = 'traded' if row[0] else 'watched'
                traded_counts[key] = row[1]

            overview = {
                'total': sum(status_counts.values()),
                'pending': status_counts.get('pending', 0),
                'in_progress': status_counts.get('in_progress', 0),
                'completed': status_counts.get('completed', 0),
                'traded_count': traded_counts.get('traded', 0),
                'watched_count': traded_counts.get('watched', 0)
            }

            # 2. Performance by trigger type for watched stocks (completed only, all stocks regardless of was_traded)
            cursor.execute("""
                SELECT
                    trigger_type,
                    COUNT(*) as count,
                    AVG(tracked_7d_return) as avg_7d_return,
                    AVG(tracked_14d_return) as avg_14d_return,
                    AVG(tracked_30d_return) as avg_30d_return,
                    SUM(CASE WHEN tracked_30d_return > 0 THEN 1 ELSE 0 END) * 1.0 /
                        NULLIF(SUM(CASE WHEN tracked_30d_return IS NOT NULL THEN 1 ELSE 0 END), 0) as win_rate_30d
                FROM analysis_performance_tracker
                WHERE tracking_status = 'completed'
                GROUP BY trigger_type
                ORDER BY count DESC
            """)

            # Simplified trigger type performance data
            trigger_performance = []
            for row in cursor.fetchall():
                trigger_type = row[0] or 'unknown'
                trigger_performance.append({
                    'trigger_type': trigger_type,
                    'count': row[1],
                    'avg_7d_return': row[2],
                    'avg_14d_return': row[3],
                    'avg_30d_return': row[4],
                    'win_rate_30d': row[5]
                })

            logger.info(f"Trigger type performance fetch completed: {len(trigger_performance)} types")

            # 3. Actual trading performance (from trading_history table, last 30 days)
            actual_trading = {}
            try:
                cursor.execute("""
                    SELECT
                        COUNT(*) as count,
                        AVG(profit_rate) as avg_profit_rate,
                        SUM(CASE WHEN profit_rate > 0 THEN 1 ELSE 0 END) as win_count,
                        SUM(CASE WHEN profit_rate <= 0 THEN 1 ELSE 0 END) as loss_count,
                        AVG(CASE WHEN profit_rate > 0 THEN profit_rate END) as avg_profit,
                        AVG(CASE WHEN profit_rate <= 0 THEN profit_rate END) as avg_loss,
                        MAX(profit_rate) as max_profit,
                        MIN(profit_rate) as max_loss,
                        SUM(CASE WHEN profit_rate > 0 THEN profit_rate ELSE 0 END) as total_profit,
                        SUM(CASE WHEN profit_rate < 0 THEN ABS(profit_rate) ELSE 0 END) as total_loss
                    FROM trading_history
                    WHERE sell_date >= date('now', '-30 days')
                """)
                row = cursor.fetchone()
                if row and row[0] > 0:
                    count = row[0]
                    win_count = row[2] or 0
                    loss_count = row[3] or 0
                    total_profit = row[8] or 0
                    total_loss = row[9] or 0
                    profit_factor = total_profit / total_loss if total_loss > 0 else None

                    # Actual trading data (profit_rate is already percentage, divide by 100)
                    actual_trading = {
                        'count': count,
                        'avg_profit_rate': (row[1] or 0) / 100,  # percentage → decimal
                        'win_rate': win_count / count if count > 0 else 0,
                        'win_count': win_count,
                        'loss_count': loss_count,
                        'avg_profit': (row[4] or 0) / 100,  # percentage → decimal
                        'avg_loss': (row[5] or 0) / 100,    # percentage → decimal
                        'max_profit': (row[6] or 0) / 100,  # percentage → decimal
                        'max_loss': (row[7] or 0) / 100,    # percentage → decimal
                        'profit_factor': profit_factor
                    }
            except sqlite3.OperationalError:
                # trading_history table does not exist
                pass

            # 4. Actual trading performance by trigger type (from trading_history)
            # trigger_type storage started from 2026-01-12 - earlier data has no trigger_type
            actual_trading_by_trigger = []
            TRIGGER_TRACKING_START_DATE = '2026-01-12'
            try:
                cursor.execute("""
                    SELECT
                        COALESCE(trigger_type, 'AI_Analysis') as trigger_type,
                        COUNT(*) as count,
                        AVG(profit_rate) as avg_profit_rate,
                        SUM(CASE WHEN profit_rate > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
                        SUM(CASE WHEN profit_rate > 0 THEN profit_rate ELSE 0 END) as total_profit,
                        SUM(CASE WHEN profit_rate < 0 THEN ABS(profit_rate) ELSE 0 END) as total_loss,
                        SUM(CASE WHEN profit_rate > 0 THEN 1 ELSE 0 END) as win_count,
                        SUM(CASE WHEN profit_rate <= 0 THEN 1 ELSE 0 END) as loss_count,
                        AVG(CASE WHEN profit_rate > 0 THEN profit_rate END) as avg_profit,
                        AVG(CASE WHEN profit_rate <= 0 THEN profit_rate END) as avg_loss
                    FROM trading_history
                    WHERE sell_date >= ?
                    GROUP BY trigger_type
                    ORDER BY count DESC
                """, (TRIGGER_TRACKING_START_DATE,))

                for row in cursor.fetchall():
                    trigger_type = row[0] or 'AI_Analysis'
                    total_profit = row[4] or 0
                    total_loss = row[5] or 0
                    profit_factor = total_profit / total_loss if total_loss > 0 else None

                    actual_trading_by_trigger.append({
                        'trigger_type': trigger_type,
                        'count': row[1],
                        'avg_profit_rate': (row[2] or 0) / 100,  # percentage → decimal
                        'win_rate': row[3] or 0,
                        'profit_factor': profit_factor,
                        'win_count': row[6] or 0,
                        'loss_count': row[7] or 0,
                        'avg_profit': (row[8] or 0) / 100 if row[8] else None,  # percentage → decimal
                        'avg_loss': (row[9] or 0) / 100 if row[9] else None     # percentage → decimal
                    })

                logger.info(f"Actual trading by trigger type: {len(actual_trading_by_trigger)} types")
            except sqlite3.OperationalError:
                # trigger_type column does not exist
                pass

            # 5. Risk-reward ratio threshold analysis
            rr_ranges = [
                (0, 1.0, '0~1.0'),
                (1.0, 1.5, '1.0~1.5'),
                (1.5, 1.75, '1.5~1.75'),
                (1.75, 2.0, '1.75~2.0'),
                (2.0, 2.5, '2.0~2.5'),
                (2.5, 100, '2.5+')
            ]

            rr_threshold_analysis = []
            for low, high, label in rr_ranges:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_count,
                        SUM(CASE WHEN was_traded = 1 THEN 1 ELSE 0 END) as traded_count,
                        SUM(CASE WHEN was_traded = 0 THEN 1 ELSE 0 END) as watched_count,
                        AVG(tracked_30d_return) as avg_all_return,
                        AVG(CASE WHEN was_traded = 0 THEN tracked_30d_return END) as avg_watched_return
                    FROM analysis_performance_tracker
                    WHERE tracking_status = 'completed'
                      AND risk_reward_ratio >= ? AND risk_reward_ratio < ?
                """, (low, high))

                row = cursor.fetchone()
                if row and row[0] > 0:
                    rr_threshold_analysis.append({
                        'range': label,
                        'total_count': row[0],
                        'traded_count': row[1] or 0,
                        'watched_count': row[2] or 0,
                        'avg_all_return': row[3],
                        'avg_watched_return': row[4]
                    })

            # 6. Missed opportunities (watched but gained 10%+)
            cursor.execute("""
                SELECT
                    ticker, company_name, trigger_type, analyzed_price,
                    tracked_30d_price, tracked_30d_return, skip_reason,
                    analyzed_date, decision
                FROM analysis_performance_tracker
                WHERE tracking_status = 'completed'
                  AND was_traded = 0
                  AND tracked_30d_return > 0.1
                ORDER BY tracked_30d_return DESC
                LIMIT 5
            """)

            missed_opportunities = []
            for row in cursor.fetchall():
                missed_opportunities.append({
                    'ticker': row[0],
                    'company_name': row[1],
                    'trigger_type': row[2] or 'unknown',
                    'analyzed_price': row[3],
                    'tracked_30d_price': row[4],
                    'tracked_30d_return': row[5],
                    'skip_reason': row[6] or '',
                    'analyzed_date': row[7] or '',
                    'decision': row[8] or ''
                })

            # 7. Avoided losses (watched and dropped 10%+)
            cursor.execute("""
                SELECT
                    ticker, company_name, trigger_type, analyzed_price,
                    tracked_30d_price, tracked_30d_return, skip_reason,
                    analyzed_date, decision
                FROM analysis_performance_tracker
                WHERE tracking_status = 'completed'
                  AND was_traded = 0
                  AND tracked_30d_return < -0.1
                ORDER BY tracked_30d_return ASC
                LIMIT 5
            """)

            avoided_losses = []
            for row in cursor.fetchall():
                avoided_losses.append({
                    'ticker': row[0],
                    'company_name': row[1],
                    'trigger_type': row[2] or 'unknown',
                    'analyzed_price': row[3],
                    'tracked_30d_price': row[4],
                    'tracked_30d_return': row[5],
                    'skip_reason': row[6] or '',
                    'analyzed_date': row[7] or '',
                    'decision': row[8] or ''
                })

            # 8. Data-driven recommendations
            recommendations = []

            # Best performing trigger recommendation (sorted by avg_30d_return, minimum 3 cases)
            if trigger_performance:
                # Filter for count >= 3, then sort by avg_30d_return
                valid_triggers = [t for t in trigger_performance
                                  if t['count'] >= 3 and t.get('avg_30d_return') is not None]
                if valid_triggers:
                    best = max(valid_triggers, key=lambda x: x['avg_30d_return'] or 0)
                    # avg_30d_return is in decimal form (e.g., 0.078 = 7.8%)
                    recommendations.append(
                        f"🏆 Best trigger: '{best['trigger_type']}' "
                        f"(30-day avg {(best['avg_30d_return'] or 0)*100:.1f}%, win rate {(best['win_rate_30d'] or 0)*100:.0f}%)"
                    )

            # Data insufficiency warning
            if overview['completed'] < 10:
                recommendations.append(
                    f"⏳ Completed tracking data is insufficient at {overview['completed']} cases. "
                    f"Recommend accumulating at least 10 cases before analysis."
                )

            logger.info(f"Performance analysis complete: {overview['total']} tracked, {overview['completed']} completed")

            return {
                'overview': overview,
                'trigger_performance': trigger_performance,
                'actual_trading': actual_trading,
                'actual_trading_by_trigger': actual_trading_by_trigger,
                'rr_threshold_analysis': rr_threshold_analysis,
                'missed_opportunities': missed_opportunities,
                'avoided_losses': avoided_losses,
                'recommendations': recommendations
            }

        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                logger.warning(f"analysis_performance_tracker table does not exist: {str(e)}")
                return self._empty_performance_analysis()
            else:
                raise
        except Exception as e:
            logger.error(f"Error collecting performance analysis data: {str(e)}")
            return self._empty_performance_analysis()

    def _empty_performance_analysis(self) -> Dict:
        """Return empty performance analysis data"""
        return {
            'overview': {
                'total': 0,
                'pending': 0,
                'in_progress': 0,
                'completed': 0,
                'traded_count': 0,
                'watched_count': 0
            },
            'trigger_performance': [],
            'actual_trading': {},
            'actual_trading_by_trigger': [],
            'rr_threshold_analysis': [],
            'missed_opportunities': [],
            'avoided_losses': [],
            'recommendations': []
        }

    def _empty_trigger_reliability(self) -> Dict:
        """Return empty trigger reliability data"""
        return {
            'trigger_reliability': [],
            'best_trigger': None,
            'last_updated': datetime.now().isoformat()
        }

    def get_trigger_reliability(self, conn) -> Dict:
        """Trigger type reliability cross-analysis (analysis accuracy + actual trading + principles)"""
        try:
            logger.info("Collecting trigger reliability data...")
            cursor = conn.cursor()

            # Trigger keyword matching map (matches principle condition text)
            TRIGGER_KEYWORDS = {
                "Volume Surge": ["volume", "surge", "turnover"],
                "Volume Surge Top Stocks": ["volume", "surge", "turnover"],
                "Gap Up Momentum Top Stocks": ["gap", "momentum", "break"],
                "Gap Up": ["gap", "momentum", "break"],
                "Technical Breakout": ["breakout", "resistance", "support"],
                "Intraday Gain Top Stocks": ["surge", "gain", "intraday"],
                "Intraday Gain": ["surge", "gain", "intraday"],
                "Closing Strength Top Stocks": ["close", "closing", "strength"],
                "Closing Strength": ["close", "closing", "strength"],
                "Consolidation with Volume Increase": ["consolidation", "sideways", "range"],
                "Sideways Volume": ["consolidation", "sideways", "range"],
                "Capital Inflow Top Stocks": ["inflow", "capital", "market cap"],
                "Capital Inflow": ["inflow", "capital", "market cap"],
                "News Trigger": ["news", "announcement", "catalyst"],
            }

            # 1. Analysis performance tracking data (analysis_performance_tracker)
            analysis_data = {}
            try:
                cursor.execute("""
                    SELECT
                        trigger_type,
                        COUNT(*) as total_tracked,
                        SUM(CASE WHEN tracking_status = 'completed' THEN 1 ELSE 0 END) as completed,
                        AVG(CASE WHEN tracking_status = 'completed' THEN tracked_30d_return END) as avg_30d_return,
                        SUM(CASE WHEN tracking_status = 'completed' AND tracked_30d_return > 0 THEN 1 ELSE 0 END) * 1.0 /
                            NULLIF(SUM(CASE WHEN tracking_status = 'completed' AND tracked_30d_return IS NOT NULL THEN 1 ELSE 0 END), 0) as win_rate_30d
                    FROM analysis_performance_tracker
                    WHERE trigger_type IS NOT NULL AND trigger_type != ''
                    GROUP BY trigger_type
                    ORDER BY total_tracked DESC
                """)
                for row in cursor.fetchall():
                    analysis_data[row[0]] = {
                        'total_tracked': row[1],
                        'completed': row[2] or 0,
                        'avg_30d_return': row[3],
                        'win_rate_30d': row[4]
                    }
                logger.info(f"Analysis data: {len(analysis_data)} trigger types")
            except sqlite3.OperationalError:
                pass

            # 2. Actual trading data (trading_history)
            trading_data = {}
            try:
                cursor.execute("""
                    SELECT
                        COALESCE(trigger_type, 'AI_Analysis') as trigger_type,
                        COUNT(*) as count,
                        SUM(CASE WHEN profit_rate > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate,
                        AVG(profit_rate) / 100.0 as avg_profit_rate,
                        SUM(CASE WHEN profit_rate > 0 THEN profit_rate ELSE 0 END) as total_profit,
                        SUM(CASE WHEN profit_rate < 0 THEN ABS(profit_rate) ELSE 0 END) as total_loss
                    FROM trading_history
                    WHERE sell_date IS NOT NULL
                    GROUP BY trigger_type
                    ORDER BY count DESC
                """)
                for row in cursor.fetchall():
                    total_profit = row[4] or 0
                    total_loss = row[5] or 0
                    trading_data[row[0]] = {
                        'count': row[1],
                        'win_rate': row[2],
                        'avg_profit_rate': row[3],
                        'profit_factor': total_profit / total_loss if total_loss > 0 else None
                    }
                logger.info(f"Trading data: {len(trading_data)} trigger types")
            except sqlite3.OperationalError:
                pass

            # 3. Trading principles data (trading_principles)
            principles = []
            try:
                cursor.execute("""
                    SELECT condition, action, confidence, supporting_trades
                    FROM trading_principles
                    WHERE scope = 'universal' AND is_active = 1
                    ORDER BY confidence DESC
                """)
                principles = [
                    {'condition': r[0], 'action': r[1], 'confidence': r[2], 'supporting_trades': r[3]}
                    for r in cursor.fetchall()
                ]
            except sqlite3.OperationalError:
                pass

            # Match principles to triggers
            def match_principles(trigger_type):
                keywords = TRIGGER_KEYWORDS.get(trigger_type, [])
                if not keywords:
                    return []
                matched = []
                for p in principles:
                    cond = p['condition'].lower()
                    if any(kw.lower() in cond for kw in keywords):
                        matched.append(p)
                return sorted(matched, key=lambda x: x['confidence'], reverse=True)[:3]

            principle_match_count = 0

            # 4. Cross combine — collect all trigger types
            all_triggers = set(analysis_data.keys()) | set(trading_data.keys())
            trigger_reliability = []

            for trigger_type in all_triggers:
                analysis = analysis_data.get(trigger_type, {})
                trading = trading_data.get(trigger_type, {})
                matched_principles = match_principles(trigger_type)
                if matched_principles:
                    principle_match_count += 1

                completed = analysis.get('completed', 0)
                analysis_win = analysis.get('win_rate_30d')
                trading_count = trading.get('count', 0)
                trading_win = trading.get('win_rate')

                # Grade calculation
                if completed < 3:
                    grade = 'D'
                elif analysis_win is not None and analysis_win >= 0.6 and trading_win is not None and trading_win >= 0.6 and trading_count >= 5:
                    grade = 'A'
                elif analysis_win is not None and analysis_win >= 0.5 and (trading_win is None or trading_win >= 0.5 or trading_count < 5):
                    grade = 'B'
                else:
                    grade = 'C'

                # Recommendation text generation
                if grade == 'A':
                    rec = f"High reliability. Active consideration recommended."
                elif grade == 'B':
                    win_pct = f"{analysis_win*100:.0f}%" if analysis_win else "N/A"
                    rec = f"Analysis accuracy acceptable ({win_pct}). Actual trading data accumulation needed."
                elif grade == 'C':
                    win_pct = f"{analysis_win*100:.0f}%" if analysis_win else "N/A"
                    rec = f"Analysis accuracy low ({win_pct}). Cautious approach needed."
                else:
                    rec = "Insufficient data. Minimum 3 completed tracking cases needed."

                trigger_reliability.append({
                    'trigger_type': trigger_type,
                    'grade': grade,
                    'analysis_accuracy': {
                        'total_tracked': analysis.get('total_tracked', 0),
                        'completed': completed,
                        'avg_30d_return': analysis.get('avg_30d_return'),
                        'win_rate_30d': analysis_win
                    },
                    'actual_trading': {
                        'count': trading_count,
                        'win_rate': trading_win,
                        'avg_profit_rate': trading.get('avg_profit_rate'),
                        'profit_factor': trading.get('profit_factor')
                    },
                    'related_principles': matched_principles,
                    'recommendation': rec
                })

            # Sort by grade (A > B > C > D), within same grade sort by completed count descending
            grade_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
            trigger_reliability.sort(key=lambda x: (
                grade_order.get(x['grade'], 4),
                -(x['analysis_accuracy'].get('completed', 0)),
                -(x['actual_trading'].get('count', 0) or 0)
            ))

            # Select best_trigger
            best_trigger = None
            if trigger_reliability:
                best_trigger = trigger_reliability[0]['trigger_type']

            logger.info(f"Principles matched: {principle_match_count} triggers linked to principles")
            logger.info(f"Trigger reliability analysis complete: {len(trigger_reliability)} triggers")

            return {
                'trigger_reliability': trigger_reliability,
                'best_trigger': best_trigger,
                'last_updated': datetime.now().isoformat()
            }

        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                logger.warning(f"Trigger reliability analysis table not found: {str(e)}")
                return self._empty_trigger_reliability()
            else:
                raise
        except Exception as e:
            logger.error(f"Error in trigger reliability analysis: {str(e)}")
            return self._empty_trigger_reliability()

    def get_jeoningu_data(self, conn) -> Dict:
        """Fetch Jeoningu contrarian investment lab data"""
        try:
            logger.info("Collecting Jeoningu lab data...")
            
            # Import for real-time price fetching
            try:
                sys.path.insert(0, str(PROJECT_ROOT / "events"))
                from jeoningu_price_fetcher import get_current_price
                PRICE_FETCHER_AVAILABLE = True
            except ImportError:
                PRICE_FETCHER_AVAILABLE = False
                logger.warning("jeoningu_price_fetcher not found. Real-time price fetching disabled.")
            
            # 1. Fetch all trading history
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM jeoningu_trades
                ORDER BY id ASC
            """)
            
            trade_history = []
            for row in cursor.fetchall():
                trade = self.dict_from_row(row, cursor)
                trade_history.append(trade)
            
            logger.info(f"Jeoningu trade history: {len(trade_history)} trades")
            
            # 2. Check current position
            current_position = None
            latest_balance = 10000000  # Default value
            initial_capital = 10000000
            
            if trade_history:
                # Find last BUY
                last_buy = None
                for trade in reversed(trade_history):
                    if trade.get('trade_type') == 'BUY':
                        last_buy = trade
                        break
                
                # Check if there's a SELL linked to this BUY
                if last_buy:
                    has_sell = any(
                        t.get('trade_type') == 'SELL' and 
                        t.get('related_buy_id') == last_buy.get('id')
                        for t in trade_history
                    )
                    
                    if not has_sell:
                        # Fetch real-time current price
                        stock_code = last_buy.get('stock_code')
                        buy_price = last_buy.get('price', 0)
                        quantity = last_buy.get('quantity', 0)
                        buy_amount = last_buy.get('amount', 0)
                        
                        if PRICE_FETCHER_AVAILABLE and stock_code:
                            try:
                                current_price = get_current_price(stock_code)
                                logger.info(f"Real-time price fetch: {stock_code} = {current_price:,} KRW")
                            except Exception as e:
                                logger.warning(f"Failed to fetch current price: {e}, using buy price")
                                current_price = buy_price
                        else:
                            current_price = buy_price
                        
                        # Calculate current value and P&L
                        current_value = quantity * current_price
                        unrealized_pl = current_value - buy_amount
                        unrealized_pl_pct = (unrealized_pl / buy_amount * 100) if buy_amount > 0 else 0
                        
                        current_position = {
                            'stock_code': stock_code,
                            'stock_name': last_buy.get('stock_name'),
                            'quantity': quantity,
                            'buy_price': buy_price,
                            'buy_amount': buy_amount,
                            'current_price': current_price,
                            'current_value': current_value,
                            'unrealized_pl': unrealized_pl,
                            'unrealized_pl_pct': unrealized_pl_pct,
                            'buy_date': last_buy.get('analyzed_date'),
                            'video_id': last_buy.get('video_id'),
                            'video_title': last_buy.get('video_title')
                        }
                
                # Latest balance
                latest_balance = trade_history[-1].get('balance_after', initial_capital)
            
            # 3. Calculate performance metrics
            sell_trades = [t for t in trade_history if t.get('trade_type') == 'SELL']
            
            winning_trades = sum(1 for t in sell_trades if t.get('profit_loss', 0) > 0)
            losing_trades = sum(1 for t in sell_trades if t.get('profit_loss', 0) < 0)
            draw_trades = sum(1 for t in sell_trades if t.get('profit_loss', 0) == 0)
            total_trades = len(sell_trades)
            
            # Win rate calculation: exclude draws, win/(win+loss)
            decided_trades = winning_trades + losing_trades
            win_rate = (winning_trades / decided_trades * 100) if decided_trades > 0 else 0
            
            # Realized P&L calculation
            realized_pl = sum(t.get('profit_loss', 0) for t in sell_trades)
            
            # Unrealized P&L (current position)
            unrealized_pl = current_position.get('unrealized_pl', 0) if current_position else 0
            
            # Total P&L = realized + unrealized
            total_pl = realized_pl + unrealized_pl
            cumulative_return = (total_pl / initial_capital * 100) if initial_capital > 0 else 0
            
            # Total assets calculation
            # Total assets = initial capital + total P&L (realized + unrealized)
            total_assets = initial_capital + total_pl
            
            avg_return_per_trade = 0
            if sell_trades:
                avg_return_per_trade = sum(t.get('profit_loss_pct', 0) for t in sell_trades) / len(sell_trades)
            
            # 4. Create timeline data (by video)
            timeline = []
            for trade in trade_history:
                timeline_entry = {
                    'video_id': trade.get('video_id'),
                    'video_title': trade.get('video_title'),
                    'video_date': trade.get('video_date'),
                    'video_url': trade.get('video_url'),
                    'analyzed_date': trade.get('analyzed_date'),
                    'jeon_sentiment': trade.get('jeon_sentiment'),
                    'jeon_reasoning': trade.get('jeon_reasoning'),
                    'contrarian_action': trade.get('contrarian_action'),
                    'trade_type': trade.get('trade_type'),
                    'stock_code': trade.get('stock_code'),
                    'stock_name': trade.get('stock_name'),
                    'notes': trade.get('notes'),
                    'profit_loss': trade.get('profit_loss'),
                    'profit_loss_pct': trade.get('profit_loss_pct')
                }
                timeline.append(timeline_entry)
            
            # 5. Cumulative return chart data (if multiple trades on same day, show only last trade)
            cumulative_chart = []
            chart_by_date = {}  # Store last trade by date
            
            for trade in trade_history:
                if trade.get('cumulative_return_pct') is not None:
                    date = trade.get('analyzed_date', '')
                    if date:
                        # Extract only date (remove time)
                        date_only = date.split('T')[0] if 'T' in date else date.split(' ')[0]
                        
                        # Overwrite same date (only last trade remains)
                        chart_by_date[date_only] = {
                            'date': date_only,
                            'cumulative_return': trade.get('cumulative_return_pct'),
                            'balance': trade.get('balance_after')
                        }
            
            # Sort by date
            cumulative_chart = sorted(chart_by_date.values(), key=lambda x: x['date'])
            
            return {
                'enabled': True,
                'summary': {
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'draw_trades': draw_trades,
                    'win_rate': win_rate,
                    'cumulative_return': cumulative_return,
                    'realized_pl': realized_pl,
                    'unrealized_pl': unrealized_pl,
                    'total_pl': total_pl,
                    'total_assets': total_assets,
                    'avg_return_per_trade': avg_return_per_trade,
                    'initial_capital': initial_capital,
                    'current_balance': latest_balance
                },
                'current_position': current_position,
                'timeline': timeline,
                'cumulative_chart': cumulative_chart,
                'trade_history': trade_history
            }
            
        except sqlite3.OperationalError as e:
            if "no such table: jeoningu_trades" in str(e):
                logger.warning("Jeoningu lab table does not exist. Returning disabled status.")
                return {
                    'enabled': False,
                    'message': 'Jeoningu lab data has not been generated yet.'
                }
            else:
                raise
        except Exception as e:
            logger.error(f"Error collecting Jeoningu lab data: {str(e)}")
            return {
                'enabled': False,
                'error': str(e)
            }
    
    def generate(self) -> Dict:
        """Generate complete dashboard data"""
        try:
            logger.info(f"Connecting to DB: {self.db_path}")
            conn = self.connect_db()
            conn.row_factory = sqlite3.Row
            
            logger.info("Starting data collection...")
            
            # Collect data from each table
            holdings = self.get_stock_holdings(conn)
            trading_history = self.get_trading_history(conn)
            watchlist = self.get_watchlist_history(conn)
            market_condition = self.get_market_condition(conn)
            holding_decisions = self.get_holding_decisions(conn)
            
            # Collect Korea Investment & Securities live trading data
            kis_data = self.get_kis_trading_data()
            real_portfolio = kis_data.get("portfolio", [])
            account_summary = kis_data.get("account_summary", {})
            
            # Collect Jeoningu lab data
            jeoningu_lab = self.get_jeoningu_data(conn)

            # Collect trading insights data
            trading_insights = self.get_trading_insights(conn)

            # Collect performance analysis data and add to trading_insights
            performance_analysis = self.get_performance_analysis(conn)
            trading_insights['performance_analysis'] = performance_analysis

            # Trigger reliability cross-analysis
            trigger_reliability = self.get_trigger_reliability(conn)
            trading_insights['trigger_reliability'] = trigger_reliability

            # Calculate summary statistics
            portfolio_summary = self.calculate_portfolio_summary(holdings)
            trading_summary = self.calculate_trading_summary(trading_history)
            ai_decision_summary = self.get_ai_decision_summary(holding_decisions)
            
            # Calculate real trading summary
            real_trading_summary = self.calculate_real_trading_summary(real_portfolio, account_summary)

            # Calculate daily Prism simulator cumulative profit
            prism_performance = self.calculate_cumulative_realized_profit(
                trading_history, market_condition
            )

            # Complete dashboard data structure
            dashboard_data = {
                'generated_at': datetime.now().isoformat(),
                'trading_mode': self.trading_mode,
                'summary': {
                    'portfolio': portfolio_summary,
                    'trading': trading_summary,
                    'ai_decisions': ai_decision_summary,
                    'real_trading': real_trading_summary
                },
                'holdings': holdings,
                'real_portfolio': real_portfolio,  # Live trading portfolio added
                'account_summary': account_summary,  # Account summary added
                'operating_costs': self.get_operating_costs(),  # Operating costs added
                'trading_history': trading_history,
                'watchlist': watchlist,
                'market_condition': market_condition,
                'prism_performance': prism_performance,  # Daily Prism simulator return added
                'holding_decisions': holding_decisions,
                'jeoningu_lab': jeoningu_lab,  # Jeoningu lab data added
                'trading_insights': trading_insights  # Trading insights data added
            }
            
            conn.close()
            
            logger.info(f"Data collection complete: {len(holdings)} holdings, {len(real_portfolio)} live, {len(trading_history)} trades, {len(watchlist)} watchlist")
            if jeoningu_lab.get('enabled'):
                logger.info(f"Jeoningu lab: {jeoningu_lab['summary']['total_trades']} trades, return {jeoningu_lab['summary']['cumulative_return']:.2f}%")
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error during data generation: {str(e)}")
            raise
    
    def save(self, data: Dict, output_file: str = None):
        """Save to JSON file"""
        try:
            if output_file is None:
                output_file = self.output_path
            
            output_path = Path(output_file)
            
            # Create directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            file_size = output_path.stat().st_size
            logger.info(f"JSON file saved: {output_path} ({file_size:,} bytes)")
            
        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            raise


def main():
    """Main execution function"""
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="Dashboard JSON Generator")
    parser.add_argument("--mode", choices=["demo", "real"], 
                       help=f"Trading mode (demo: simulation, real: live trading, default: {_cfg.get('default_mode', 'demo')})")
    parser.add_argument("--no-translation", action="store_true",
                       help="Disable English translation (generate Korean version only)")
    
    args = parser.parse_args()
    
    async def async_main():
        try:
            logger.info("=== Starting Dashboard JSON Generation ===")
            
            enable_translation = not args.no_translation
            generator = DashboardDataGenerator(
                trading_mode=args.mode,
                enable_translation=enable_translation
            )
            
            # Generate Korean data
            logger.info("Generating Korean data...")
            dashboard_data_ko = generator.generate()
            
            # Save Korean JSON file
            ko_output = str(SCRIPT_DIR / "dashboard" / "public" / "dashboard_data.json")
            generator.save(dashboard_data_ko, ko_output)
            
            # English translation and save
            if generator.enable_translation:
                try:
                    logger.info("Starting English translation...")
                    dashboard_data_en = await generator.translator.translate_dashboard_data(dashboard_data_ko)
                    
                    # Save English JSON file
                    en_output = str(SCRIPT_DIR / "dashboard" / "public" / "dashboard_data_en.json")
                    generator.save(dashboard_data_en, en_output)
                    
                    logger.info("English translation complete!")
                except Exception as e:
                    logger.error(f"Error during English translation: {str(e)}")
                    logger.warning("Only Korean version was generated.")
            else:
                logger.info("Translation feature disabled. Only Korean version generated.")
            
            logger.info("=== Dashboard JSON Generation Complete ===")
            
        except Exception as e:
            logger.error(f"Error during execution: {str(e)}")
            exit(1)
    
    # Run asyncio event loop
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
