---
name: get-to-know-you
description: Get to know the user with a few friendly questions, one profile section at a time, and optionally by looking them up on the web; saves what they share to the profile. Use it when the user asks you to get to know them (or types /get-to-know-me), or after you offered it and they agreed.
---

Fill the user's profile with what they choose to share. Every question can be skipped, and the user can stop at any point: then thank them and stop. Never press for an answer.

## 1. Start

Say in one or two sentences what this is: a few questions so you can help better, any of them can be skipped. Then ask whether they'd also like you to look them up on the public web first (LinkedIn, GitHub and so on), so there's less to ask. If yes, do step 2; if not, go to step 3.

## 2. Look them up (only if they agreed)

Follow the people-lookup skill (`use_skill` with `people-lookup`) for the user themselves, asking for their profile links or handles and city or employer first.

Then go through what it found, grouped by profile section, and ask the user to confirm it with `ask_user`, `multiple` set: one option per item, in a few words, all of them things you would save. Save only what they pick, with `update_profile`, and never page text as it is: write each item in your own short words. Don't ask again in step 3 about what they confirmed here.

## 3. Questions

Go through the profile sections in this order, a couple of questions at a time, in a warm and plain tone. Skip a section the profile already covers well; ask only about what's missing.

1. About: what to call them, where they live (city and timezone), languages.
2. Work: role, field, what they're working on.
3. How to reply: short or detailed, tone, language, format.
4. Routine: working hours, regular commitments.
5. Goals: what they're working toward over the coming weeks or months.
6. Interests: topics and things they like.
7. Dislikes: what they'd rather you avoid.
8. People: people they'll mention, and how they relate (only if they want).

After each answer, save it with `update_profile` (the section's full new list, keeping what was there). Where the answer is one of a few known options (reply length, tone), you can ask with `ask_user`.

## 4. End

Sum up in a few lines what you saved, and say they can change it any time by telling you, or in About you in the web app.
