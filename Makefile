# agent-email: install the command, the one Google command, the skill and the background service.
SHELL := /bin/bash

SKILL     := agent-email
HOME_DIR  := $(HOME)/.agent-email
SHARE     := $(HOME)/.local/share/agent-email
BIN       := $(HOME)/.local/bin/agent-email
LABEL     := com.agent-email.listener
UID       := $(shell id -u)
TOOL_DIRS := $(shell for t in herdr aim uv; do p=$$(command -v $$t 2>/dev/null) && dirname "$$p"; done | awk '!seen[$$0]++' | paste -sd: -)
SERVICE_PATH := $(HOME)/.local/bin:$(HOME)/.cargo/bin:$(TOOL_DIRS):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
SKILL_DIRS := $(HOME)/.agents/skills $(HOME)/.claude/skills

.PHONY: install install_cli install_skill machine_file install_service links verify_install test

# MACHINE names this machine, once: make install MACHINE=laptop. GWS_BIN is the real Google CLI, if it isn't found.
install: install_cli install_skill machine_file install_service
	@$(BIN) doctor
	@echo "Installed. 'make links' then points the gws commands here."

install_cli:
	@test -f "$(HOME_DIR)/config.json" || { mkdir -p "$(HOME_DIR)"; cp config.example.json "$(HOME_DIR)/config.json"; echo "Fill in $(HOME_DIR)/config.json (see README), then run make install again."; exit 1; }
	uv tool install --force --reinstall .
	@mkdir -p "$(SHARE)"
	@install -m 755 bin/gws-account "$(SHARE)/gws-account"

# Copied over what's there. A file dropped from the skill stays behind until someone removes it; verify_install says so.
install_skill:
	@for dir in $(SKILL_DIRS); do \
		mkdir -p "$$dir/$(SKILL)"; cp -R "skills/$(SKILL)/." "$$dir/$(SKILL)/"; \
		echo "skill installed in $$dir/$(SKILL)"; \
	done

machine_file:
	@test -f "$(HOME_DIR)/machine.json" || { \
		test -n "$(MACHINE)" || { echo "Say which machine this is: make install MACHINE=<name>"; exit 1; }; \
		gws_bin="$(GWS_BIN)"; \
		if [ -z "$$gws_bin" ]; then for c in /opt/homebrew/bin/gws /usr/local/bin/gws; do [ -x "$$c" ] && gws_bin=$$c && break; done; fi; \
		test -n "$$gws_bin" || { echo "Couldn't find the Google CLI; set GWS_BIN"; exit 1; }; \
		printf '{"name": "%s", "gws_bin": "%s"}\n' "$(MACHINE)" "$$gws_bin" > "$(HOME_DIR)/machine.json"; \
	}

install_service:
	@mkdir -p "$(HOME_DIR)/logs"
	@if [ "$$(uname)" = "Darwin" ]; then \
		plist="$(HOME)/Library/LaunchAgents/$(LABEL).plist"; \
		new=$$(sed -e 's|@BIN@|$(BIN)|g' -e 's|@HOME@|$(HOME)|g' -e 's|@PATH@|$(SERVICE_PATH)|g' launchd/listener.plist.in); \
		if launchctl print gui/$(UID)/$(LABEL) >/dev/null 2>&1 && [ "$$new" = "$$(cat "$$plist" 2>/dev/null)" ]; then \
			launchctl kickstart -k gui/$(UID)/$(LABEL); echo "service restarted"; exit 0; \
		fi; \
		launchctl bootout gui/$(UID)/$(LABEL) 2>/dev/null || true; sleep 1; \
		mkdir -p "$(HOME)/Library/LaunchAgents"; printf '%s\n' "$$new" > "$$plist"; \
		launchctl bootstrap gui/$(UID) "$$plist" || launchctl bootstrap user/$(UID) "$$plist"; echo "service started"; \
	else \
		mkdir -p "$(HOME)/.config/systemd/user"; \
		sed -e 's|@BIN@|$(BIN)|g' -e 's|@HOME@|$(HOME)|g' -e 's|@PATH@|$(SERVICE_PATH)|g' systemd/agent-email.service.in > "$(HOME)/.config/systemd/user/agent-email.service"; \
		systemctl --user daemon-reload; systemctl --user enable --now agent-email.service; systemctl --user restart agent-email.service; echo "service started"; \
	fi

links:
	@$(BIN) links

verify_install:
	@for dir in $(SKILL_DIRS); do diff -rq "skills/$(SKILL)" "$$dir/$(SKILL)" >/dev/null || { echo "FAIL: $$dir/$(SKILL) differs from the repo"; exit 1; }; done
	@$(BIN) doctor

test:
	uv run pytest -q
