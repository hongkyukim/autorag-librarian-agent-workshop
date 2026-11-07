PYTHON ?= python3
export PYTHONPATH := src

.PHONY: demo test eval eval-bad gate gate-bad mcp-probe live live-run clean

demo:
	$(PYTHON) -m autorag_lab demo

test:
	$(PYTHON) -m unittest discover -s tests -v

eval:
	$(PYTHON) -m autorag_lab eval -v

eval-bad:
	@for m in hallucinate_citation stale_version obey_injection; do $(PYTHON) -m autorag_lab eval --model $$m; done

gate:
	$(PYTHON) -m autorag_lab gate

# Every misbehaving model must FAIL the gate; this target fails if one passes.
gate-bad:
	@for m in hallucinate_citation stale_version obey_injection; do \
		if $(PYTHON) -m autorag_lab gate --model $$m; then echo "!! $$m passed the gate"; exit 1; fi; \
	done; echo "OK: every bad model was blocked"

mcp-probe:
	@printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | $(PYTHON) -m autorag_lab mcp --read-only

live:
	$(PYTHON) extensions/live/autorag_live.py

live-run:
	$(PYTHON) extensions/live/autorag_live.py --run

clean:
	rm -rf out .autorag
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
