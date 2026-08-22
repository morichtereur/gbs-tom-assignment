.PHONY: install snapshot classify eval run stability dashboard test all clean

PY = .venv/bin/python
export PYTHONPATH := src

install:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

# Pull the activity set, the directly-follows graph and the city panel from the
# two upstream repositories. Writes the committed snapshot under data/.
snapshot:
	$(PY) scripts/snapshot_inputs.py

# Two-stage work-family classification. Needs ANTHROPIC_API_KEY for stage 2;
# `make classify-offline` runs stage 1 only and says so in the readout.
classify:
	$(PY) -m tom.classify

classify-offline:
	$(PY) -m tom.classify --offline

# Score the classifier against the hand-labelled gold set. The stability run
# needs this: it resamples labels at the measured error rate.
eval:
	$(PY) eval/eval_classify.py

# The analysis. Solves the ladder, the ablation and the forced-position probes,
# then writes RESULTS.md.
run:
	$(PY) -m tom.report

# 10,000 draws over every declared quantity. Takes about an hour on eight cores.
stability:
	$(PY) -m tom.stability

dashboard:
	$(PY) -m tom.dashboard

test:
	$(PY) -m pytest tests -q

all: snapshot classify eval run stability run dashboard

clean:
	rm -f dashboard.html RESULTS.md data/results.json data/stability.json
