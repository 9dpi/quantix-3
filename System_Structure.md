Quantix AI Core – System Structure (Multi‑Agent Edition)
🧠 Tổng quan kiến trúc: Multi‑Agent Distributed Intelligence
Quantix AI Core được tái cấu trúc thành một hệ thống multi‑agent phân tán, nơi mỗi tác vụ chuyên biệt được đảm nhận bởi một AI Agent độc lập. Các agent giao tiếp với nhau qua message bus (Redis Pub/Sub) và phối hợp hoạt động theo luồng xử lý 5 giai đoạn, mô phỏng quy trình làm việc của một quỹ đầu tư tổ chức.

Kiến trúc này kế thừa toàn bộ sức mạnh của các module tính toán SMC (StructureEngineV1, ConfidenceRefiner, Janitor, EntryCalculator) và bổ sung khả năng suy luận linh hoạt của các LLM agent, cho phép hệ thống thích ứng với nhiều điều kiện thị trường khác nhau.

🗺️ Luồng xử lý 5 giai đoạn
Giai đoạn	Nhóm Agent	Mô tả
Stage 1 – Thu thập & chuẩn bị dữ liệu	Market Data Agents	Đồng bộ dữ liệu từ nhiều nguồn (Binance, Twelve Data, Pepperstone), xử lý làm sạch, phát hiện bất thường (anomaly).
Stage 2 – Phân tích cấu trúc thị trường	Structure Analysis Agents	Áp dụng logic SMC để phát hiện BOS, FVG, thanh khoản, xác định các vùng giá tiềm năng.
Stage 3 – Đánh giá tín hiệu & xác nhận	Signal Validation Agents	Tổng hợp các tín hiệu từ Stage 2, tính confidence score, lọc theo phiên giao dịch, kiểm tra chéo với nguồn giá độc lập.
Stage 4 – Quản lý rủi ro & tối ưu hóa	Risk Management Agents	Đánh giá tỷ lệ R:R, áp dụng circuit breaker, tính toán khối lượng vào lệnh dựa trên ATR và mức độ tự tin.
Stage 5 – Ra quyết định & thực thi	Decision Agent	Tổng hợp ý kiến từ các agent trước, quyết định phát hành tín hiệu, cập nhật trạng thái lệnh, kích hoạt các hành động healing nếu cần.
🤖 Các Agent chi tiết
Stage 1: Market Data Agents
Data Fetcher Agent

Vai trò: Lấy dữ liệu OHLCV theo chu kỳ (M15, H1) từ các nguồn chính (Binance) và dự phòng (Twelve Data).

Công cụ: Module feeds/ hiện tại, có cơ chế failover tự động.

Đầu ra: Dữ liệu đã chuẩn hóa gửi vào message bus.

Data Quality Agent

Vai trò: Kiểm tra tính toàn vẹn dữ liệu (gap, spike), ghi nhận bất thường vào bảng validation_events.

Công cụ: Thuật toán phát hiện outlier dựa trên ATR.

Đầu ra: Cảnh báo nếu chất lượng dữ liệu dưới ngưỡng.

Stage 2: Structure Analysis Agents
BOS Detector Agent

Vai trò: Phát hiện Break of Structure (BOS) theo cả hai chiều, yêu cầu xác nhận bằng body close.

Công cụ: Gọi StructureEngineV1.detect_bos().

Đầu ra: Các mốc BOS kèm mức độ mạnh/yếu.

FVG Locator Agent

Vai trò: Xác định các Fair Value Gaps (FVG) trên khung M15, phân loại theo kích thước và vị trí.

Công cụ: StructureEngineV1.identify_fvg().

Đầu ra: Danh sách vùng FVG có thể dùng để vào lệnh.

Liquidity Sweep Agent

Vai trò: Phát hiện các cú quét thanh khoản tại các vùng đỉnh/đáy phiên Á, London, New York.

Công cụ: Module engine/liquidity.py.

Đầu ra: Các mức giá thanh khoản đã bị quét.

Stage 3: Signal Validation Agents
Confidence Scorer Agent

Vai trò: Tính điểm tin cậy dựa trên mô hình trọng số (Structure 30%, Session 25%, Volatility 20%, Trend 25%).

Công cụ: ConfidenceRefiner.calculate().

Đầu ra: Confidence score (0–100), chỉ phát hành nếu ≥80%.

Session Filter Agent

Vai trò: Loại bỏ tín hiệu trong các giờ chết (Dead Zone: Chủ nhật, thanh khoản thấp, rollover).

Công cụ: MarketHours utility.

Đầu ra: Tín hiệu đã được lọc theo thời gian.

Price Validator Agent

Vai trò: Kiểm tra chéo giá hiện tại với nguồn thứ hai (Pepperstone), ghi nhận chênh lệch.

Công cụ: InstitutionalValidator (chạy độc lập).

Đầu ra: Cảnh báo nếu slippage vượt ngưỡng.

Stage 4: Risk Management Agents
R:R Optimizer Agent

Vai trò: Tính toán mức Take Profit và Stop Loss dựa trên ATR và loại phiên (PEAK/HIGH/LOW).

Công cụ: EntryCalculator.compute_rr().

Đầu ra: Cặp TP/SL tối ưu.

Circuit Breaker Agent

Vai trò: Theo dõi số lượng tín hiệu active, thời gian cooldown, ngăn chặn spam.

Công cụ: Logic anti‑burst (20 phút cooldown, global lock).

Đầu ra: Quyết định cho phép/ từ chối tín hiệu mới.

Position Sizing Agent

Vai trò: Đề xuất khối lượng vào lệnh dựa trên confidence score và ATR.

Công cụ: Công thức Kelly Criterion điều chỉnh.

Đầu ra: Khối lượng (lot) đề xuất.

Stage 5: Decision & Execution Agents
Signal Dispatcher Agent

Vai trò: Quyết định cuối cùng có phát hành tín hiệu hay không, ghi vào bảng fx_signals, gửi thông báo Telegram.

Công cụ: Gọi API Telegram, ghi Supabase.

Đầu ra: Tín hiệu mới (nếu có).

Watcher Agent

Vai trò: Theo dõi trạng thái các lệnh active, cập nhật khi chạm entry, SL, TP, timeout 180 phút.

Công cụ: SignalWatcher logic, nhưng chạy dưới dạng agent riêng.

Đầu ra: Cập nhật trạng thái lệnh, kích hoạt trailing stop (breakeven lock).

Healing Agent (thay thế Watchdog)

Vai trò: Giám sát sức khỏe các agent khác qua heartbeat, tự động khởi động lại agent bị treo, giải phóng tín hiệu stuck.

Công cụ: Janitor + cơ chế active healing.

Đầu ra: Cảnh báo admin, chạy cleanup.

🔗 Cơ chế giao tiếp giữa các agent
Message Bus: Redis Pub/Sub (dùng Redis add‑on trên Railway). Mỗi agent đăng ký nhận các kênh liên quan đến nhiệm vụ của mình.

Định dạng tin nhắn: JSON, bao gồm agent_id, stage, payload, timestamp.

State persistence: Các agent không giữ trạng thái nội bộ; mọi kết quả quan trọng đều được ghi vào Supabase để đảm bảo tính nhất quán và dễ dàng khôi phục khi agent khởi động lại.

Đồng bộ hóa: Ở một số giai đoạn (ví dụ Stage 2 → Stage 3), cần đợi đủ kết quả từ tất cả agent trong nhóm. Sử dụng Redis Streams với consumer groups để đảm bảo xử lý tuần tự và không mất dữ liệu.

🗄️ Database Schema (giữ nguyên, bổ sung nếu cần)
Table	Vai trò	Ghi chú
fx_signals	Lưu tất cả tín hiệu đã phát hành	Thêm trường agent_decision_log để ghi lại ý kiến các agent
fx_analysis_log	Log chi tiết hoạt động của từng agent	Dùng cho debug và cải thiện hiệu suất
fx_signal_validation	Kết quả kiểm tra chéo giá	Không thay đổi
agent_heartbeat	Ghi nhận trạng thái hoạt động của từng agent	Healing agent dùng để phát hiện agent chết
market_data_cache	Cache dữ liệu OHLCV từ nhiều nguồn	Giảm tải API, tăng tốc xử lý
🧩 Các thành phần engine hiện có (được gọi từ agent)
Tất cả các module dưới đây vẫn được giữ nguyên và đóng gói thành tools mà agent có thể gọi:

StructureEngineV1: Phát hiện BOS, FVG, thanh khoản.

ConfidenceRefiner: Tính điểm tin cậy.

EntryCalculator: Tính toán entry, TP, SL dựa trên FVG.

Janitor: Dọn dẹp tín hiệu stuck.

MarketHours: Xác định phiên giao dịch, dead zone.

InstitutionalValidator: Kiểm tra chéo giá.

Các module này được giữ nguyên code Python thuần (không LLM) để đảm bảo tốc độ và độ chính xác. Agent chỉ có nhiệm vụ gọi chúng đúng lúc và tổng hợp kết quả.

🏗️ Kiến trúc triển khai
Local Development
Mỗi agent là một tiến trình Python riêng, chạy đồng thời bằng docker-compose hoặc foreman (dựa trên Procfile).

Redis chạy trong container riêng.

Supabase local (hoặc dùng remote cho dữ liệu thật).

Triển khai lên Railway
Mỗi agent là một service riêng trong Railway, được định nghĩa trong Procfile với câu lệnh python agent_xxx.py.

Sử dụng Redis add‑on của Railway làm message bus.

Biến môi trường chứa API keys, database connection, Redis URL.

procfile
# Procfile
web: python start_railway_web.py
agent_data: python agent_data_fetcher.py
agent_bos: python agent_bos_detector.py
agent_fvg: python agent_fvg_locator.py
agent_liquidity: python agent_liquidity.py
agent_confidence: python agent_confidence.py
agent_session: python agent_session_filter.py
agent_validator: python agent_validator.py
agent_rr: python agent_rr_optimizer.py
agent_circuit: python agent_circuit_breaker.py
agent_sizing: python agent_position_sizing.py
agent_dispatcher: python agent_dispatcher.py
agent_watcher: python agent_watcher.py
agent_healing: python agent_healing.py
📁 Repository Map (cập nhật)
text
Quantix_AI_Core/
├── backend/
│   ├── quantix_core/
│   │   ├── agents/               # Mỗi agent một file .py
│   │   │   ├── base_agent.py      # Lớp cơ sở (kết nối Redis, logging)
│   │   │   ├── data_fetcher.py
│   │   │   ├── bos_detector.py
│   │   │   ├── fvg_locator.py
│   │   │   ├── liquidity.py
│   │   │   ├── confidence.py
│   │   │   ├── session_filter.py
│   │   │   ├── price_validator.py
│   │   │   ├── rr_optimizer.py
│   │   │   ├── circuit_breaker.py
│   │   │   ├── position_sizing.py
│   │   │   ├── dispatcher.py
│   │   │   ├── watcher.py
│   │   │   └── healing.py
│   │   ├── engine/               # Giữ nguyên: structure_engine, confidence_refiner, v.v.
│   │   ├── feeds/                 # Giữ nguyên: data connectors
│   │   ├── utils/                  # Market hours, calculator, v.v.
│   │   ├── database/               # Kết nối Supabase
│   │   └── api/                     # Web API (FastAPI)
│   ├── dashboard/                   # Giao diện (HTML/JS)
├── Procfile                          # Định nghĩa các service trên Railway
├── docker-compose.yml                # Cho môi trường local
└── requirements.txt                  # Bao gồm redis, crewai (nếu cần), v.v.
🔄 Luồng hoạt động mẫu
Data Fetcher Agent lấy dữ liệu mỗi 5 phút, publish vào kênh raw_data.

BOS Detector, FVG Locator, Liquidity Agent cùng lắng nghe, mỗi agent tính toán và publish kết quả riêng.

Confidence Scorer lắng nghe tổng hợp từ Stage 2, tính điểm và publish.

Session Filter kiểm tra thời gian, nếu hợp lệ thì chuyển tiếp.

R:R Optimizer và Circuit Breaker chạy song song, đưa ra khuyến nghị.

Signal Dispatcher thu thập tất cả, nếu confidence ≥80% và circuit breaker cho phép, phát hành tín hiệu.

Watcher Agent theo dõi tín hiệu active, cập nhật trạng thái.

Healing Agent nhận heartbeat từ tất cả agent, nếu thiếu heartbeat 15 phút → restart agent qua Railway API (hoặc ghi log để admin xử lý).

🛡️ Bảo mật và nhất quán
RLS (Row Level Security) vẫn được bật trên Supabase.

Message bus không chứa dữ liệu nhạy cảm, chỉ chứa ID và kết quả phân tích.

Atomic transitions trong Watcher Agent: sử dụng database lock để tránh trùng lặp thông báo Telegram.

Dead letter queue cho các message xử lý lỗi, Healing Agent sẽ xem xét định kỳ.

📈 Chiến lược nâng cấp sau này
Dần thay thế một số agent bằng LLM để có khả năng phân tích tin tức, sentiment.

Tích hợp thêm agent học tăng cường (RL) để tự điều chỉnh tham số dựa trên hiệu suất lịch sử.

Mở rộng số lượng cặp tiền và khung thời gian.

Version: 4.0 (Multi‑Agent)
Trạng thái: Thiết kế hoàn chỉnh, sẵn sàng phát triển.
Ngày: 2025-04-02

Tài liệu này mô tả kiến trúc tổng thể. Chi tiết từng agent sẽ được triển khai trong quá trình phát triển.

---

# 📋 KẾ HOẠCH TRIỂN KHAI — Implementation Roadmap

> Cập nhật: 2026-03-04 | Baseline: v4.0 Multi-Agent Architecture

## Tài sản kế thừa từ Quantix_AI_Core (Monolithic)

| Module | File gốc | Tái sử dụng |
|--------|----------|-------------|
| StructureEngineV1 | `engine/structure_engine_v1.py` | ✅ Copy nguyên |
| ConfidenceRefiner | `engine/confidence_refiner.py` | ✅ Copy nguyên |
| SignalWatcher | `engine/signal_watcher.py` | ✅ Refactor thành Watcher Agent |
| Janitor | `engine/janitor.py` | ✅ Tích hợp vào Healing Agent |
| Watchdog | `engine/watchdog.py` | ✅ Tích hợp vào Healing Agent |
| EntryCalculator | `utils/entry_calculator.py` | ✅ Copy nguyên |
| MarketHours | `utils/market_hours.py` | ✅ Copy nguyên |
| Data Feeds | `feeds/binance_feed.py`, `multi_broker_feed.py` | ✅ Copy + thêm interface |
| Database | `database/` | ✅ Copy + migrate schema |
| Notifications | `notifications/` | ✅ Copy nguyên |

---

## 🔷 PHASE 1: Foundation & Infrastructure (Tuần 1–2)

**Mục tiêu**: Dựng nền tảng kỹ thuật — base agent, message bus, DB schema.

| # | Task | Chi tiết | Status |
|---|------|----------|--------|
| 1.1 | Project Scaffolding | Cấu trúc thư mục, `requirements.txt`, `docker-compose.yml`, `.env.example` | ✅ |
| 1.2 | Base Agent Framework | `agents/base_agent.py` — Redis Pub/Sub, heartbeat, logging, graceful shutdown, retry | ✅ |
| 1.3 | Message Bus Layer | `messaging/bus.py` — JSON format, channel naming, Redis Streams consumer groups, DLQ | ✅ |
| 1.4 | Database Migration | Copy `database/`, thêm tables: `agent_heartbeat`, `market_data_cache`, column `agent_decision_log` | ✅ |
| 1.5 | Engine Modules Copy | Copy engine + feeds + utils từ Quantix_AI_Core, verify unit tests pass | ✅ |

**Deliverables**: Base agent chạy được local (docker-compose), heartbeat verify, DB schema mới trên Supabase staging.

---

## 🔷 PHASE 2: Stage 1–2 Agents — Data & Analysis (Tuần 3–4)

**Mục tiêu**: Nhóm agents thu thập dữ liệu + phân tích cấu trúc thị trường.

| # | Agent | Subscribe | Publish | Engine Module |
|---|-------|-----------|---------|---------------|
| 2.1 | Data Fetcher Agent | Timer (5 phút) | `stage_1.raw_data` | `feeds/binance_feed.py` |
| 2.2 | Data Quality Agent | `stage_1.raw_data` | `stage_1.validated_data` | ATR outlier detection |
| 2.3 | BOS Detector Agent | `stage_1.validated_data` | `stage_2.bos_result` | `StructureEngineV1.detect_bos()` |
| 2.4 | FVG Locator Agent | `stage_1.validated_data` | `stage_2.fvg_result` | `StructureEngineV1.identify_fvg()` |
| 2.5 | Liquidity Sweep Agent | `stage_1.validated_data` | `stage_2.liquidity_result` | `engine/liquidity.py` |

**Deliverables**: 5 agents chạy đồng thời, dữ liệu chảy từ Feed → Quality → BOS/FVG/Liquidity.

---

## 🔷 PHASE 3: Stage 3–4 Agents — Validation & Risk (Tuần 5–6)

**Mục tiêu**: Nhóm agents đánh giá tín hiệu + quản lý rủi ro.

| # | Agent | Subscribe | Publish | Logic |
|---|-------|-----------|---------|-------|
| 3.1 | Confidence Scorer | `stage_2.*` (đợi đủ 3) | `stage_3.confidence_result` | `ConfidenceRefiner.calculate()` |
| 3.2 | Session Filter | `stage_3.confidence_result` | `stage_3.filtered_signal` | `MarketHours` dead-zone check |
| 3.3 | Price Validator | `stage_3.filtered_signal` | `stage_3.validated_signal` | Cross-check Pepperstone/TwelveData |
| 3.4 | R:R Optimizer | `stage_3.validated_signal` | `stage_4.rr_result` | `EntryCalculator.compute_rr()` |
| 3.5 | Circuit Breaker | `stage_3.validated_signal` | `stage_4.circuit_result` | Cooldown 20 min, max active, global lock |
| 3.6 | Position Sizing | `stage_4.rr_result` | `stage_4.sizing_result` | Kelly Criterion + ATR |

**Lưu ý kỹ thuật**: Confidence Scorer phải đợi đủ 3 kết quả từ Stage 2 (BOS + FVG + Liquidity) qua correlation_id matching trước khi tính score.

**Deliverables**: Pipeline hoàn chỉnh Stage 1→4, circuit breaker hoạt động, signal correlation verified.

---

## 🔷 PHASE 4: Stage 5 — Decision & Execution (Tuần 7–8)

**Mục tiêu**: Tầng ra quyết định cuối cùng + thực thi + self-healing.

| # | Agent | Vai trò | Kế thừa từ |
|---|-------|---------|------------|
| 4.1 | Signal Dispatcher | Quyết định phát hành, ghi DB, gửi Telegram | Analyzer logic |
| 4.2 | Watcher Agent | Theo dõi lệnh active, breakeven, trailing stop | `signal_watcher.py` |
| 4.3 | Healing Agent | Monitor heartbeat, restart agent chết, cleanup stuck | `watchdog.py` + `janitor.py` |
| 4.4 | Web API Service | Dashboard API (FastAPI), WebSocket real-time | `api/` |

**Deliverables**: End-to-end pipeline hoàn chỉnh, Telegram hoạt động, Healing Agent phục hồi agent chết.

---

## 🔷 PHASE 5: Testing, Shadow Mode & Production (Tuần 9–12)

**Mục tiêu**: Đảm bảo chất lượng + chuyển đổi production an toàn.

| # | Task | Thời gian | Chi tiết |
|---|------|-----------|----------|
| 5.1 | Integration Testing | Tuần 9 | Unit + E2E tests, agent communication tests |
| 5.2 | Shadow Mode | Tuần 10–11 | Chạy song song hệ thống cũ + mới, so sánh kết quả, KHÔNG gửi Telegram từ hệ mới |
| 5.3 | Production Cutover | Tuần 12 | Deploy lên Railway (13+ services), monitor 48h, bật auto-healing |
| 5.4 | Dashboard Migration | Tuần 12 | Thêm Agent Status panel, Pipeline Visualization |

**Deliverables**: 100% test pass, shadow mode 2 tuần clean, production live với monitoring.

---

## 📊 Tổng kết Timeline

| Phase | Nội dung | Tuần | Status |
|-------|----------|------|--------|
| Phase 1 | Foundation & Infrastructure | 1–2 | ✅ Hoàn thành |
| Phase 2 | Stage 1–2 Agents (Data + Analysis) | 3–4 | ✅ Hoàn thành |
| Phase 3 | Stage 3–4 Agents (Validation + Risk) | 5–6 | ✅ Hoàn thành |
| Phase 4 | Stage 5 Agents (Decision + Execution) | 7–8 | ✅ Hoàn thành |
| Phase 5 | Testing + Shadow + Production | 9–12 | 🔶 Sẵn sàng |

**Tổng thời gian ước tính: 10–12 tuần**

---

## 🔐 Nguyên tắc triển khai

1. **Không phá vỡ production hiện tại** — Hệ thống cũ chạy song song cho đến khi hệ mới pass shadow mode
2. **Engine modules giữ nguyên** — Không refactor logic tính toán SMC, chỉ wrap thành tools cho agents
3. **Mỗi agent = 1 service Railway** — Độc lập, có thể restart riêng lẻ
4. **Heartbeat bắt buộc** — Mọi agent phải gửi heartbeat, Healing Agent giám sát
5. **Logging chuẩn hóa** — Loguru format thống nhất, correlation_id xuyên suốt pipeline