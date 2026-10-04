package main

import (
	"fmt"
	"hash/fnv"
	"math"
	"sort"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

// referenceNow is the FIXED "current time" the whole service reasons about.
// Pinning it makes every time-windowed answer (log `since`, metric series)
// deterministic and reproducible across runs and machines.
var referenceNow = time.Date(2026, time.June, 30, 11, 5, 0, 0, time.UTC)

// knownServices is the closed set of services the mock telemetry covers.
var knownServices = []string{"checkout", "payments", "search-api", "cart"}

// logEntry is a single seeded log line held in memory (time as time.Time).
type logEntry struct {
	ts      time.Time
	level   string
	service string
	message string
	traceID string // empty means "no trace id"
}

// seedLog is the compact form used to declare seed data: agoSec is how many
// seconds before referenceNow the line was emitted.
type seedLog struct {
	agoSec  int
	level   string
	message string
	traceID string
}

// runbook is a seeded runbook document.
type runbook struct {
	slug    string
	title   string
	content string
	version string
}

// Store holds all seeded telemetry and the ticket counter. It is safe for
// concurrent use: the seed data is read-only after construction and the ticket
// counter is updated atomically.
type Store struct {
	logs        map[string][]logEntry // service -> lines, sorted newest-first
	runbooks    map[string]runbook    // slug -> runbook
	ticketSeq   atomic.Int64          // ticket id counter; first id is 1001
	metricNames []string              // metrics advertised in docs/tests
}

// NewStore builds a Store populated with the deterministic seed data.
func NewStore() *Store {
	s := &Store{
		logs:        make(map[string][]logEntry),
		runbooks:    make(map[string]runbook),
		metricNames: []string{"latency_p99_ms", "error_rate", "cpu_saturation_pct", "restart_count"},
	}
	// The atomic starts at 1000 so the first AddInt64(1) yields 1001.
	s.ticketSeq.Store(1000)

	for svc, seeds := range seedLogs() {
		entries := make([]logEntry, 0, len(seeds))
		for _, sl := range seeds {
			entries = append(entries, logEntry{
				ts:      referenceNow.Add(-time.Duration(sl.agoSec) * time.Second),
				level:   sl.level,
				service: svc,
				message: sl.message,
				traceID: sl.traceID,
			})
		}
		// Present newest-first; tie-break on message for a stable order.
		sort.SliceStable(entries, func(i, j int) bool {
			if entries[i].ts.Equal(entries[j].ts) {
				return entries[i].message < entries[j].message
			}
			return entries[i].ts.After(entries[j].ts)
		})
		s.logs[svc] = entries
	}

	for _, rb := range seedRunbooks() {
		s.runbooks[rb.slug] = rb
	}
	return s
}

// ---------------------------------------------------------------------------
// Logs
// ---------------------------------------------------------------------------

// SearchLogs returns the seeded lines for service whose message or level
// contains query (case-insensitive) and that fall within the `since` window
// relative to referenceNow. limit caps the returned lines; truncated reports
// whether more lines matched than were returned.
//
// since is assumed pre-validated (validSince); an unparseable value is treated
// as "no lower bound" so the handler's validation stays the single gatekeeper.
func (s *Store) SearchLogs(service, query, since string, limit int) logsSearchResponse {
	lower := strings.ToLower(query)
	windowStart, ok := windowStartFor(since, referenceNow)

	matched := make([]logEntry, 0, 16)
	for _, e := range s.logs[service] {
		if ok && e.ts.Before(windowStart) {
			continue
		}
		if lower != "" &&
			!strings.Contains(strings.ToLower(e.message), lower) &&
			!strings.Contains(strings.ToLower(e.level), lower) {
			continue
		}
		matched = append(matched, e)
	}

	total := len(matched)
	if limit < 0 {
		limit = 0
	}
	truncated := false
	if limit < total {
		matched = matched[:limit]
		truncated = true
	}

	lines := make([]logLine, 0, len(matched))
	for _, e := range matched {
		lines = append(lines, logLine{
			Timestamp: e.ts.UTC().Format(time.RFC3339),
			Level:     e.level,
			Service:   e.service,
			Message:   e.message,
			TraceID:   e.traceID,
		})
	}
	return logsSearchResponse{Lines: lines, TotalMatched: total, Truncated: truncated}
}

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------

// QueryMetrics returns a deterministic time series for service/metric. The
// points step by `step` from (now - since) up to now inclusive. Values are a
// fixed function of service, metric, aggregation, and index — no randomness —
// and trend toward each service's incident peak at the latest point.
func (s *Store) QueryMetrics(service, metric, aggregation, since, step string) metricsQueryResponse {
	windowStart, ok := windowStartFor(since, referenceNow)
	if !ok {
		windowStart = referenceNow.Add(-time.Hour)
	}
	stepDur := parseRelativeWindow(step)
	if stepDur <= 0 {
		stepDur = time.Minute
	}

	// Collect the timestamps first so values can be a function of the total
	// count (needed for the "ramp toward now" shape).
	const maxPoints = 1000
	var stamps []time.Time
	for t := windowStart; !t.After(referenceNow); t = t.Add(stepDur) {
		stamps = append(stamps, t)
		if len(stamps) >= maxPoints {
			break
		}
	}

	series := make([]metricPoint, 0, len(stamps))
	n := len(stamps)
	for i, t := range stamps {
		series = append(series, metricPoint{
			T: t.UTC().Format(time.RFC3339),
			V: metricValue(service, metric, aggregation, i, n),
		})
	}

	return metricsQueryResponse{
		Metric:      metric,
		Unit:        unitFor(metric),
		Aggregation: aggregation,
		Series:      series,
	}
}

// unitFor returns a sensible unit string for a metric name.
func unitFor(metric string) string {
	switch metric {
	case "latency_p99_ms":
		return "ms"
	case "error_rate":
		return "ratio"
	case "cpu_saturation_pct":
		return "percent"
	case "restart_count":
		return "count"
	default:
		return "count"
	}
}

// metricRange returns the (low, high) bounds the series ramps across for a
// given service/metric. Incident-specific combinations peak high (e.g. checkout
// latency above 2000ms); everything else stays in a healthy band.
func metricRange(service, metric string) (lo, hi float64) {
	switch service + "|" + metric {
	case "checkout|latency_p99_ms":
		return 850, 2200 // DB pool exhaustion -> latency spike above SLO
	case "payments|error_rate":
		return 0.02, 0.42 // upstream 5xx storm
	case "search-api|cpu_saturation_pct":
		return 70, 98 // CPU saturation
	case "cart|restart_count":
		return 1, 14 // crash loop / OOM restarts climbing
	}
	switch metric {
	case "latency_p99_ms":
		return 120, 185
	case "error_rate":
		return 0.001, 0.012
	case "cpu_saturation_pct":
		return 28, 52
	case "restart_count":
		return 0, 0
	default:
		return 1, 10
	}
}

// aggMultiplier scales the headline value by aggregation so p99 > p95 > avg,
// which is what an operator expects from a latency-style metric.
func aggMultiplier(aggregation string) float64 {
	switch aggregation {
	case "p50":
		return 0.62
	case "avg":
		return 0.70
	case "p95":
		return 0.93
	case "p99":
		return 1.00
	case "max":
		return 1.08
	case "rate":
		return 1.00
	default:
		return 1.00
	}
}

// metricValue computes the deterministic value at index i of n total points.
func metricValue(service, metric, aggregation string, i, n int) float64 {
	lo, hi := metricRange(service, metric)

	frac := 1.0
	if n > 1 {
		frac = float64(i) / float64(n-1)
	}
	base := (lo + (hi-lo)*frac) * aggMultiplier(aggregation)

	// Deterministic jitter so the curve is not a perfectly straight line.
	span := hi - lo
	if span == 0 {
		span = math.Abs(base)
	}
	jitter := (hashFrac(service, metric, strconv.Itoa(i)) - 0.5) * span * 0.06
	v := base + jitter

	switch metric {
	case "error_rate":
		return roundTo(clamp(v, 0, 1), 4)
	case "cpu_saturation_pct":
		return roundTo(clamp(v, 0, 100), 1)
	case "restart_count":
		return math.Round(math.Max(0, v))
	case "latency_p99_ms":
		return roundTo(math.Max(0, v), 1)
	default:
		return roundTo(math.Max(0, v), 3)
	}
}

// hashFrac maps the joined parts to a stable value in [0, 1).
func hashFrac(parts ...string) float64 {
	h := fnv.New32a()
	for _, p := range parts {
		_, _ = h.Write([]byte(p))
		_, _ = h.Write([]byte{0})
	}
	return float64(h.Sum32()%10000) / 10000.0
}

func clamp(v, lo, hi float64) float64 {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func roundTo(v float64, decimals int) float64 {
	p := math.Pow(10, float64(decimals))
	return math.Round(v*p) / p
}

// ---------------------------------------------------------------------------
// Runbooks
// ---------------------------------------------------------------------------

// GetRunbook returns the runbook for slug. When section is non-empty and a
// matching "## <section>" heading exists, content is narrowed to that section.
// The boolean is false when the slug is unknown.
func (s *Store) GetRunbook(slug, section string) (runbookResponse, bool) {
	rb, ok := s.runbooks[slug]
	if !ok {
		return runbookResponse{}, false
	}
	content := rb.content
	if section != "" {
		if sec, found := extractSection(rb.content, section); found {
			content = sec
		}
	}
	return runbookResponse{Slug: rb.slug, Title: rb.title, Content: content, Version: rb.version}, true
}

// extractSection returns the body of the "## <section>" heading (heading
// included), up to the next "## " heading or end of document.
func extractSection(content, section string) (string, bool) {
	target := strings.ToLower(strings.TrimSpace(section))
	var buf []string
	inSection := false
	for _, ln := range strings.Split(content, "\n") {
		if strings.HasPrefix(ln, "## ") {
			if inSection {
				break // reached the next section
			}
			head := strings.ToLower(strings.TrimSpace(strings.TrimPrefix(ln, "## ")))
			if head == target {
				inSection = true
				buf = append(buf, ln)
			}
			continue
		}
		if inSection {
			buf = append(buf, ln)
		}
	}
	if !inSection {
		return "", false
	}
	return strings.TrimRight(strings.Join(buf, "\n"), "\n"), true
}

// ---------------------------------------------------------------------------
// Tickets
// ---------------------------------------------------------------------------

// CreateTicket allocates the next ticket id atomically and returns the result.
// status is "escalated" when escalate is true, otherwise "open".
func (s *Store) CreateTicket(escalate bool) ticketResponse {
	id := s.ticketSeq.Add(1)
	ticketID := fmt.Sprintf("TCK-%d", id)
	status := "open"
	if escalate {
		status = "escalated"
	}
	return ticketResponse{
		TicketID: ticketID,
		URL:      "https://tickets.local/" + ticketID,
		Status:   status,
	}
}

// ---------------------------------------------------------------------------
// Time-window helpers
// ---------------------------------------------------------------------------

// windowStartFor resolves a `since` value (relative like "15m" or an RFC3339
// instant) into an absolute lower bound. The bool is false when since carries
// no parseable bound.
func windowStartFor(since string, now time.Time) (time.Time, bool) {
	if since == "" {
		return time.Time{}, false
	}
	if d := parseRelativeWindow(since); d > 0 {
		return now.Add(-d), true
	}
	if t, err := time.Parse(time.RFC3339, since); err == nil {
		return t, true
	}
	return time.Time{}, false
}

// parseRelativeWindow parses a "<n><unit>" window (s, m, h, d). It returns 0 if
// the string is not a relative window.
func parseRelativeWindow(s string) time.Duration {
	if len(s) < 2 {
		return 0
	}
	unit := s[len(s)-1]
	num, err := strconv.Atoi(s[:len(s)-1])
	if err != nil || num < 0 {
		return 0
	}
	switch unit {
	case 's':
		return time.Duration(num) * time.Second
	case 'm':
		return time.Duration(num) * time.Minute
	case 'h':
		return time.Duration(num) * time.Hour
	case 'd':
		return time.Duration(num) * 24 * time.Hour
	default:
		return 0
	}
}
