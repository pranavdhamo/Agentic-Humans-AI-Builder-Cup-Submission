# This repo in plain English

## The one-sentence version
Many big banks still run their credit card systems on **mainframes**, giant 1970s-style computers running code in a language called **COBOL**. This repo is a practice mainframe application, plus a small copy running on Google Cloud, so people can test tools that move old systems to modern ones.

## The big idea: "legacy migration"
- **Legacy system:** old software that still does important work (like moving money around), but is hard to change, runs on expensive hardware, and few people know how to maintain it.
- **Migration / modernization:** moving that software to modern technology (cloud, Java, Python and so on) without breaking it.
- **The problem:** you can't safely practise on a real bank's system. You need a realistic fake one.
- **The solution:** **CardDemo**, a fake credit card company application that Amazon (AWS) published for exactly this purpose. The data is made up.

## What is in this repo

| Folder / file | What it is |
|---|---|
| `aws-mainframe-modernization-carddemo/` | The fake credit card app: COBOL code, screens, batch jobs, sample data and diagrams. This is the "before" system, written for a mainframe. |
| `gcp-legacy-env/` | Scripts that run part of that app on a small virtual computer in Google Cloud, so there is a live "before" system without owning a mainframe. |
| `AWS_card_demo.jpeg` | One of the diagrams (explained below). |
| `gcp-legacy-env/RESTART-VM.md` | How to start, use and stop the Google Cloud computer so you don't waste credit. |

## What the fake company does
CardDemo is a credit card company's back office. It handles:
- **Accounts:** a customer's credit line and balance.
- **Cards:** the physical or virtual cards linked to an account.
- **Transactions:** every purchase, payment and fee.
- **Bill payment:** paying off a balance.
- **Statements and reports:** summaries of activity.
- **Users:** staff who log in, either regular users or admins.

It works in two modes:
1. **Online (interactive):** staff use menus on a black-and-green terminal screen. This needs special mainframe software called CICS.
2. **Batch (overnight):** programs that run with nobody watching and process piles of work, like banks do overnight.

## What we actually ran on Google Cloud
Only the **batch** part, using a free tool called GnuCOBOL that mimics a mainframe well enough.

1. **POSTTRAN:** takes the day's list of 338 transactions and checks each one. 300 were accepted and recorded. 38 were rejected, for example because of a bad card or an over-limit account. Rejects are saved in a separate file.
2. **INTCALC:** goes through the accounts and calculates the interest owed.

Think of it as the "end of day" job at a bank. The "38 rejected" result is normal and expected. It is the program saying "some entries had problems".

**What we could not run:** the interactive screens (CICS) and the optional database and messaging parts (IMS, Db2, MQ). They need real mainframe software. They are in the repo as source code to read and study.

## Explaining the diagrams
All diagrams live in `aws-mainframe-modernization-carddemo/diagrams/`.

### 1. User flow: "what a regular employee can do"
![User flow](aws-mainframe-modernization-carddemo/diagrams/Application-Flow-User.png)

A family tree of the app's screens. Read it top to bottom.
- A person **logs in**, lands on the **Main Menu**, and picks a branch.
- **Orange boxes** are features in the basic app. **Blue boxes** are optional extras.
- Branches:
  - **Account Management:** view or change an account.
  - **Card Management:** view a card, change a card, or list all cards.
  - **Transactions:** look at one, list them, add one, or request a report.
  - **Bill Pay:** pay off the balance.
  - **Authorizations** (blue, optional): see purchases that were approved but not yet final, and flag suspicious ones as fraud.

### 2. Admin flow: "what the boss can do"
![Admin flow](aws-mainframe-modernization-carddemo/diagrams/Application-Flow-Admin.png)

Same layout, for administrators.
- **User Management:** add, update, list or delete staff logins.
- **Transaction Type Management** (blue, optional): view or edit the list of purchase types, such as groceries or fuel.

### 3. The three screenshots
These are real screens from the app. They look old because mainframes use text-only terminals.

| Screenshot | What you are looking at |
|---|---|
| ![Sign-on](aws-mainframe-modernization-carddemo/diagrams/Signon-Screen.png) **Sign-on screen** | The login page. Type an 8-character user ID and password. The ASCII-art banknote is from the fictional country "Kicsland". |
| ![Main menu](aws-mainframe-modernization-carddemo/diagrams/Main-Menu.png) **Main menu** | The 11 things a regular user can pick: account view/update, card list/view/update, transaction list/view/add/reports, bill payment, and pending authorizations. Typing a number opens that screen. |
| ![Admin menu](aws-mainframe-modernization-carddemo/diagrams/Admin-Menu.png) **Admin menu** | The admin's six options: four for managing user logins and two for managing transaction types. |

### 4. The big architecture picture ("how a card swipe gets approved")
![Architecture](aws-mainframe-modernization-carddemo/diagrams/auth_flow.png)

(This is the same picture as `AWS_card_demo.jpeg`.) It shows what happens when someone **swipes a card**. It is the optional "Authorizations" feature.

**Top box, AWS Cloud (modern world):**
1. A shopper swipes their card at a payment terminal.
2. A **Payment Network Emulator** pretends to be Visa or Mastercard sending the request.
3. **API Gateway** is the front door that receives it.
4. **Lambda** is a small piece of cloud code that passes it on.

**Big grey box, Online CICS Environment (the mainframe):**
5. The request goes into a **message queue** (MQ), like a mailbox that holds requests until the mainframe is ready.
6. A mainframe **Authorization program** [A.0] wakes up, reads the request and decides approve or decline. To decide, it looks up the **Account**, **Customer** and **Xref** (card-to-account link) databases, shown as the three cylinders on the right.
7. It saves the decision in the **Pending Authorization database** (the big dark circle) and sends the answer back through a second queue (Reply MQ). The answer travels back up to the shopper's terminal.

**Left side, a bank employee at a screen:**
8. **Authorization Summary** [S.0] shows a list of recent approvals.
9. **Authorization Details** [S.1] shows one in full.
10. **Mark Fraud** [S.2] flags it as suspicious and writes it to a separate **Fraud database**.

**Bottom box, Batch Environment:**
11. A **Pending Auth Purge Job** [B.0] runs on a schedule (the clock icon) and cleans out old authorizations.

**Why it matters:** this single picture mixes modern cloud pieces with old mainframe pieces. That mix is typical of real banks, and it is what migration tools have to untangle.

### 5. The authorization screens
| Screenshot | What it shows |
|---|---|
| ![Summary](aws-mainframe-modernization-carddemo/diagrams/auth_summary.png) **Authorization summary** | One customer (Mariane Fadel) with her credit limit (7,542.00), balance (624.23) and a list of recent approved purchases. Type `S` next to one to open it. |
| ![Details](aws-mainframe-modernization-carddemo/diagrams/auth_details.png) **Authorization details** | One purchase in full: a 25.24 charge at Amazon.com, status "0000-APPROVED". Pressing F5 marks it as fraud. |
| ![Fraud](aws-mainframe-modernization-carddemo/diagrams/auth_fraud.png) **Marked as fraud** | The same screen after pressing F5. The red "AUTH MARKED FRAUD…" message appears, and the Fraud Status field now shows a fraud flag with the date. |

### 6. The two database diagrams
These are **blueprints of how data is stored**, like the column headings of a spreadsheet.

**IMS model** ![IMS model](aws-mainframe-modernization-carddemo/diagrams/ims_model.png)
- Stores the pending authorizations in a "parent and children" layout.
- **PEND AUTH ROOT:** one record per account, with its credit limit, balance and counts of approved and declined purchases.
- **PEND AUTH DETAILS:** many records under each account, one per purchase (merchant, amount, response, fraud status and so on).
- It connects to the **account**, **customer** and **customer_card_xref** tables, which are lookup tables linking cards to customers and accounts.

**Db2 model** ![Db2 model](aws-mainframe-modernization-carddemo/diagrams/db2_model.png)
- The **AUTH FRAUDS** table.
- Each row is one purchase flagged as fraud. It is identified by card number plus timestamp, and holds the same purchase details plus the fraud report date.
- This is a normal relational database (like a spreadsheet with strict columns), unlike IMS.

**Data model file** (`CARDDEMO-DataModel.drawio`)
- An editable diagram of the main data files (accounts, cards, customers, transactions). It opens in [draw.io](https://app.diagrams.net). I could not render it here, so I have not described its contents.

## Glossary

| Term | Plain meaning |
|---|---|
| **Mainframe** | A very large, very reliable computer used by banks and airlines. |
| **COBOL** | The decades-old programming language mainframe business software is written in. |
| **CICS** | Mainframe software that lets many people use the app through screens at once. |
| **Batch job** | A program that runs on its own on a big pile of data, usually overnight. |
| **JCL** | The instruction sheet that tells the mainframe which batch programs to run, and in what order. |
| **VSAM** | The mainframe's way of storing data in files, like a very fast filing cabinet. |
| **Db2 / IMS** | Two kinds of mainframe database. |
| **MQ** | A mailbox system that lets programs pass messages to each other reliably. |
| **Authorization** | The instant yes or no when you swipe a card. |
| **GnuCOBOL** | A free tool that runs COBOL on ordinary computers, used here to stand in for the mainframe. |
| **VM** | A virtual computer rented from Google Cloud. |

## How to look at it yourself
- **Read the story visually:** open the diagrams above.
- **See it run:** follow `gcp-legacy-env/RESTART-VM.md` to start the Google Cloud computer, run the overnight job and read the results. Stop the computer afterwards so it does not use credit.
