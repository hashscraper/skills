# HashScraper Agent Skills

Collect public web data from your AI agent. Ask "What is the price of this Coupang product now?" or "Collect 50 Naver blog posts about Seongsu-dong cafes" and the `hashscraper` skill picks a ready-made HashScraper bot, runs it through the HashScraper API, and returns clean rows.

- 120+ bots for 50+ sites: Coupang, Naver (blog, cafe, news, shopping, maps), Instagram, YouTube, Olive Young, Musinsa, Kurly, KREAM, Google/Kakao maps, app stores, community boards and more.
- No scraper code and no browser on your side. Python 3 (standard library only) runs the bundled script.
- Every account gets free credits every day. The skill uses only the daily free credits unless you tell it to use your own.

Homepage: https://www.hashscraper.com/?utm_source=github&utm_medium=skill&utm_campaign=skills_repo

## Install

### Claude Code (plugin marketplace)

```text
/plugin marketplace add hashscraper/skills
/plugin install hashscraper@hashscraper
```

Or from your shell:

```bash
claude plugin marketplace add hashscraper/skills
claude plugin install hashscraper@hashscraper
```

### Other agents (skills CLI)

```bash
npx skills add hashscraper/skills
```

### Copy the folder

```bash
git clone https://github.com/hashscraper/skills.git hashscraper-skills
mkdir -p ~/.claude/skills ~/.codex/skills
cp -r hashscraper-skills/hashscraper ~/.claude/skills/   # Claude Code
cp -r hashscraper-skills/hashscraper ~/.codex/skills/    # Codex
```

## Connect once

Ask your agent to connect HashScraper (or just ask for some data). The first time, it runs the skill's `login`, which prints a link and an 8-character code. To run it yourself, use the script inside the installed skill folder, for example:

```bash
python3 ~/.claude/skills/hashscraper/scripts/hashscraper.py login   # folder copy for Claude Code
python3 ~/.codex/skills/hashscraper/scripts/hashscraper.py login    # folder copy for Codex
python3 hashscraper-skills/hashscraper/scripts/hashscraper.py login # from the cloned repository
```

Open the link, sign in (or sign up for free with Google or email), check that the code matches, and click **Approve and connect**. The script saves a new API key on your computer. You never copy or paste the key.

Instead of `login`, you can set your own key from **My page → API** in `HASHSCRAPER_API_KEY`.

## Free credits

- Free credits refill every day at midnight (KST). Unused credits do not carry over.
- Each bot costs a fixed number of credits per collected row (`credits_per_row` in `hashscraper/catalog.json`).
- When today's free credits run out, the skill stops and tells you when they refill. It uses your own credits only when you ask (`--use-credits`).

## Data and privacy

The skill collects public pages only and never asks for a site login. It talks only to the HashScraper API (`https://www.hashscraper.com/v5/api`). The API key is saved in `~/.config/hashscraper/credentials`, readable only by you, and is never printed. Run the same script with `logout` to delete it, or turn the key off in **My page → API & integrations**.

## What is inside

| Path | What it is |
|---|---|
| `hashscraper/SKILL.md` | Instructions for the agent |
| `hashscraper/catalog.json` | The bots in this bundle, their inputs and credits per row |
| `hashscraper/scripts/hashscraper.py` | The script the agent runs (`login`, `rotate`, `logout`, `catalog`, `me`, `run`, `fetch`) |
| `.claude-plugin/` | Claude Code plugin and marketplace settings |

Need daily scheduled collection or large volumes? Talk to us: https://www.hashscraper.com/quotes/new?utm_source=github&utm_medium=skill&utm_campaign=skills_repo

## License

MIT. See [LICENSE](LICENSE).

---

## 한국어

HashScraper(해시스크래퍼)의 수집 봇 120여 개(쿠팡·네이버 블로그/카페/뉴스·인스타그램·유튜브·올리브영·무신사·지도·리뷰·커뮤니티 등)를 AI 도구에서 바로 씁니다.

- **설치**: Claude Code 는 `/plugin marketplace add hashscraper/skills` → `/plugin install hashscraper@hashscraper`. 다른 도구는 `npx skills add hashscraper/skills`, 또는 `hashscraper` 폴더를 `~/.claude/skills/`·`~/.codex/skills/` 에 복사합니다.
- **처음 연결**: AI 도구에 "HashScraper 연결해 줘"라고 하면 skill 이 `login` 을 실행합니다(직접 하려면 설치한 skill 폴더의 스크립트 — 예: `python3 ~/.claude/skills/hashscraper/scripts/hashscraper.py login`) → 나온 주소를 열어 로그인(없으면 무료 가입) → 코드 확인 → **허락하고 연결**. 키는 내 컴퓨터에만 저장되고 화면에 나오지 않습니다.
- **비용**: 매일 무료 크레딧이 채워집니다(한국 시각 자정, 이월 없음). 기본으로 무료 크레딧만 쓰고, 내 크레딧은 원할 때만(`--use-credits`) 씁니다.
- **데이터**: 공개 페이지만 모으고 사이트 로그인 정보를 묻지 않습니다.
- 홈페이지: https://www.hashscraper.com/?utm_source=github&utm_medium=skill&utm_campaign=skills_repo
