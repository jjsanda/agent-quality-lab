package main

import "testing"

// The Python agent's offline engine requests runbooks by generic category slug; the live service
// must resolve those (alongside the service-specific ones) while still 404-ing unknown slugs.
func TestGenericRunbooksResolve(t *testing.T) {
	s := newTestStore()
	generic := []string{
		"latency-troubleshooting",
		"error-rate-troubleshooting",
		"saturation-troubleshooting",
		"crash-loop-recovery",
		"deploy-rollback",
		"dependency-outage-response",
		"data-integrity-response",
		"general-incident-response",
	}
	for _, slug := range generic {
		rb, ok := s.GetRunbook(slug, "")
		if !ok || rb.Content == "" {
			t.Fatalf("expected generic runbook %q to resolve with content", slug)
		}
	}
	if _, ok := s.GetRunbook("no-such-runbook", ""); ok {
		t.Fatalf("expected unknown slug to 404")
	}
}
