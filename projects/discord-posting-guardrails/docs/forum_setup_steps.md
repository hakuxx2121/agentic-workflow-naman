# Moving NDTL weekly threads to a forum channel (for Naman)

**Why:** a webhook can only create a new thread (a "post") in a **forum** channel. #trade-plans (channel ${DISCORD_ID}) is a text channel: the Nov 4 attempt got HTTP 400 "Webhooks can only create threads in forum channels". Today's `--new-thread --dry-run` check confirms that the TradeTracker webhook (ID ${DISCORD_ID}) points at ${DISCORD_ID}. A webhook can't report whether that channel is a forum, so the script prints a warning.

**Can #trade-plans just be converted?** No. Discord has no "convert text channel to forum" option. The Forum Channels FAQ (support.discord.com/hc/en-us/articles/6208479917079) only covers creating a new forum channel, and a request to add conversion is still an open feature request. Forum channels also need **Community** enabled on the server.

## Timing
Do this **after Friday 11/6's last update (8 PM) and before the 11/9 weekly thread is created.** As soon as the webhook moves, it can't post into this week's thread (${DISCORD_ID}). The pre-check will refuse those posts with a "webhook points at channel …" error, so nothing lands in the wrong place, but the updates won't go out.

## Steps (Discord desktop or web)
1. **Check that Community is on.** Go to Server Settings > Community. If you see "Enable Community", turn it on and follow the setup screens (it asks for a rules channel and an updates channel). If it's already on, skip this step.
2. **Create the forum.** In the channel list, hover over the category that holds #trade-plans and click **+**. Choose **Forum** as the channel type, name it `trade-plans` (rename the old channel first, e.g. to `trade-plans-archive`, so the names don't clash). Click **Create Channel**.
3. **Copy the permissions.** Open the new channel's Edit Channel > Permissions and match #trade-plans: same roles and the same view/post rights. A simple setup is to let members reply in posts but only let you and the webhook create posts.
4. **Point the webhook at the forum.** Go to Server Settings > Integrations > Webhooks and click **TradeTracker** (ID ${DISCORD_ID}). In the **Channel** dropdown, pick the new `trade-plans` forum, then click **Save Changes**. **Do not** click "Copy Webhook URL", regenerate, or delete it. Moving the webhook keeps the same URL and token, so nothing needs to be re-shared.
5. Optional: make the old channel read-only (Edit Channel > Permissions > @everyone > Send Messages and Send Messages in Threads off) and pin a note that points to the new forum.

## What happens to the existing threads
- Nothing moves. The old threads stay where they are, including NDTL weekly ${DISCORD_ID} and AI Earnings ${DISCORD_ID}. Their history and links keep working.
- The webhook can't post into the old threads any more, because the pre-check requires the thread's parent to be the webhook's channel. Any later edit to an old message would also be refused.
- The old update and receipt files in the working directory are unaffected.

## What I need from you afterwards
Just reply **"done"**. I'll then:
1. Run `post_webhook.py … --check-only` (a read-only GET) to read the webhook's new channel ID.
2. Write that ID into `poster/config.json` (`forum_channel_id`) and set `forum_type_confirmed: true`.
3. Dry-run `--new-thread "NDTL - Weekly Trade Plan 11/9/26"` against the new channel, then create the real weekly post with a slot.
4. Put the new thread URL in that week's levels.json.
