# bade-import

This script adds GitHub avatars to pretix orders. To make this work you'll have to create two questions within pretalx:

 1. Ask users for their GitHub username.
 2. A hidden file upload question that will be used for the avatar.

Take note of both questions ID's as you'll have to pass them to the script.


```shell
$ python3 import.py <github_user_question_id> <hidden_file_question_id>
```

The scrip will then retrieve all the GitHub user names from the questions (and deal with removing leading `@`'s etc.) and fetch the corresponding avatar from the GitHub API.

Once an avatar has been retrieved it will be cached locally and only downloaded again if the username changes.
