# Live demo narration — speech-synced highlight version (British female voice)

## intro
- Hello, and welcome. In this demonstration we'll watch the Jira Auto-Triage application working against a real Jira Cloud site.   →  highlights: title
- Whenever a defect is raised in Jira, the app reads the full ticket,   →  highlights: b1
- including any screenshots attached to it.   →  highlights: b2
- It checks whether the same problem has been reported before,   →  highlights: b3
- and if so, points the team straight to the earlier fix.   →  highlights: b4
- Everything is then written back into Jira. Let's walk through each step.   →  highlights: b5

## jira_before
- Here is a real defect ticket, SCRUM sixteen, in the Bug Tracking project. A Jira ticket has a few key parts.   →  highlights: none
- The summary: login page throws error five hundred when signing in.   →  highlights: summary
- The description, where the reporter explains what went wrong.   →  highlights: desc
- An attachment; in this case, a screenshot of the actual error page.   →  highlights: attach
- And on the right, the details panel, with the status 'To Do', the priority, and the labels, which are currently empty.   →  highlights: panel
- The project also holds twenty existing bug tickets. Among them, SCRUM fifteen, the very same login crash, was already fixed and closed, with the fix recorded in a comment.   →  highlights: scrum15
- That history is exactly what the app is about to exploit.   →  highlights: scrum15

## dryrun
- Step one: a dry run. The app analyses everything, but writes nothing back to Jira. Watch the log.   →  highlights: cmd
- It loads all twenty bugs from the project, as its knowledge base.   →  highlights: corpus
- It picks up SCRUM sixteen, and downloads the attached screenshot.   →  highlights: pickup
- A I vision then reads the image, finding the exact error: a null pointer exception at session manager, line forty two.   →  highlights: vision
- It compares the ticket against every existing defect, and confirms: SCRUM sixteen is a duplicate of SCRUM fifteen, with ninety five percent confidence.   →  highlights: dup16
- Crucially, it surfaces the past resolution: fixed in release two point four point one.   →  highlights: past16
- SCRUM eighteen, the checkout problem, is likewise caught as a duplicate of the payment timeout, with its own past fix surfaced.   →  highlights: dup18
- And SCRUM twenty three, which is genuinely new, receives a root cause and a suggested fix instead.   →  highlights: new23

## realrun
- Step two: the real run. The app now writes its findings back to Jira, through the standard Jira A P Is.   →  highlights: cmd
- For each ticket, it posts the triage report as a comment. You can see the two-oh-one Created responses, from the live site.   →  highlights: comments
- It adds the labels auto-triaged, and auto-dup, so triaged tickets are easy to filter.   →  highlights: labels
- And it creates a proper duplicate link, connecting SCRUM sixteen to the original, SCRUM fifteen.   →  highlights: links
- These were real A P I calls. The tickets on the live Jira site have genuinely been updated.   →  highlights: logged

## jira_after
- And here is the proof, on the real ticket. SCRUM sixteen now carries both labels.   →  highlights: labels
- A linked work item records that it duplicates SCRUM fifteen.   →  highlights: link
- And the full auto-triage comment sits on the ticket: the duplicate verdict, and the past resolution,   →  highlights: verdict
- the root cause, the severity, and the evidence read from the screenshot.   →  highlights: rest
- Anyone opening this ticket now knows, instantly, that the fix already exists in release two point four point one.   →  highlights: pastres

## phase2 (added in v2 — inserted before outro, ~39s)
- Before we finish, here is a look ahead, at phase two.   →  highlights: title
- The plan is to bring this solution into the H S B C Agentic Hub dashboard, as a shared, multi-tenant service.   →  highlights: hub
- Multiple teams across the bank can onboard their own Jira projects to the agent, through a simple, self-service flow.   →  highlights: teams
- Each team becomes its own tenant, with its own projects, its own data, and its own triage rules.   →  highlights: caps
- And the agent works strictly within each team's boundary. Duplicate matching never crosses tenants, so one team's tickets are never read against another's.   →  highlights: boundary
- The hub dashboard then gives every team its own view: triage activity, duplicates caught, and engineering hours saved.   →  highlights: metrics

## outro
- That's the Jira Auto-Triage application.   →  highlights: title
- Duplicates caught, with past fixes surfaced.   →  highlights: c12
- New defects analysed, and everything logged back into Jira, automatically.   →  highlights: c34
- Thank you very much for watching.   →  highlights: thanks
