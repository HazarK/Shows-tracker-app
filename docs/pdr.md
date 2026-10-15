## 1. Overview

TV Season Tracker is a Telegram bot that helps users keep track of TV shows they watch across different streaming platforms and alerts them when a new season becomes available.

The **MVP** focuses on a simple workflow: users manually add shows they want to follow, and the bot periodically checks an external TV-show database for new seasons.

## 2. Target User

The target user is someone who occasionally watches TV shows across multiple platforms such as Netflix, Apple TV+, Prime Video, and others.

Because their shows are spread across different services, they do not have a single place that reliably tells them when a new season of a show they follow has been released.

## 3. Problem

Users may finish a season of a show and then forget about it while waiting for the next season. When a new season is released months or years later, the streaming platform may not notify them, or the user may no longer be actively using that platform.

The product should provide a simple, centralized way to track shows and receive alerts when new seasons become available.

## 4. MVP

### Interface

The **MVP** will be implemented as a Telegram bot. No dedicated mobile or web application will be built initially.

### Adding a Show

The user enters a command such as:

`/add Severance`

The input is free text.

The system searches an external TV-show database **API** for the show. If multiple or ambiguous results are found, the system presents the most likely match to the user and asks for confirmation before saving it.

Example: `I found *Severance (**2022**)*. Is this the show you want to follow?`

The user can confirm or reject the result.

Once confirmed, the show is stored in the application's database.

### Viewing Tracked Shows

The user can request the list of currently tracked shows using a command such as:

`/list`

### Removing a Show

The user can stop tracking a show using a command such as:

`/remove Severance`

## 5. New Season Alerts

A scheduled background process runs once per day.

For every tracked show, the system checks the external TV-show database and compares the current season information with the information stored locally.

For the **MVP**, a **new season** is defined as:

> A numbered season that has a known release date and whose release date has passed. >

Specials or *Season 0* are ignored.

When a newly released season is detected, the bot sends the user a Telegram message.

Example:

`🎬 New season available: Severance — Season 3`

The system records that the notification was sent.

The same season should **not be reported again on subsequent days**.

This means the scheduled process does not simply search for *shows released in the last week.* Instead, it compares external data with the application's stored state and only alerts the user about events they have not already been notified about.

## 6. Core Flow

### Adding a Show

User opens Telegram bot

→ User sends `/add <show name>`

→ Bot receives free-text input

→ System searches TV-show database **API**

→ System identifies likely result

→ User confirms the result

→ Show is saved in the database

### Checking for New Seasons

Scheduled process runs

→ Load all tracked shows

→ Query TV-show **API** for current season information

→ Compare **API** data with stored data

→ Detect newly released seasons

→ Send Telegram notification

→ Record notification as sent

## 7. External Data

The system will use a third-party TV-show database **API**, such as **TMDB**, to retrieve:

- Show title
- Show ID
- Release year
- Existing seasons
- Season numbers
- Season release dates

The external **API**'s unique show ID should be stored rather than relying only on the show title.

## 8. AI / LLM Usage

An **LLM** may be used to interpret ambiguous free-text input and help identify the show the user means.

However, the external TV database is the source of truth.

The **LLM** should not invent show information or determine whether a new season exists.

For straightforward searches, the system may eventually perform normal **API** search without an **LLM** to reduce complexity and cost.

## 9. Error Handling

### Show Not Found

If the external **API** cannot find a matching show:

`I couldn't find a show matching *XYZ*. Try another title.`

### Ambiguous Result

If several shows match the query, present possible matches and ask the user to select one.

### External Service Unavailable

If the TV database **API** is unavailable, inform the user that the request could not be completed and allow them to retry later.

The scheduled season-checking process should log the failure and try again during the next scheduled run.

### Empty Database

If the user has not added any shows and runs `/list`:

`You aren't following any shows yet. Use /add <show name> to add one.`

If the scheduled process finds no tracked shows, it should terminate without performing external **API** requests.

## 10. Out of Scope for MVP

The following functionality will not be included initially:

- Dedicated Android or web application
- Username/password authentication
- Direct integrations with Netflix, Apple TV+, Prime Video, or other streaming services
- Determining whether a season is available on a specific streaming service
- Personalized show recommendations
- Tracking watched episodes
- Recording ratings
- Show reviews
- Social features

## 11. Possible Phase 2 Features

Future versions could include:

- Personalized show recommendations
- User ratings
- Multiple users
- Android application
- Notification preferences
- Upcoming-season reminders

## 12. MVP Success Criteria

The **MVP** is successful if a user can:

## Add a TV show using natural-language input.

## Confirm that the correct show was identified. 
## View and remove tracked shows. 
## Receive a Telegram notification when a newly released season is detected. 
## Receive only one notification for each new season.