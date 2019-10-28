from dialog_bot_sdk.bot import DialogBot
from dialog_bot_sdk import interactive_media
import grpc
import os
import json
import time
import sqlite3
from dotenv import load_dotenv


class Bot:
    def __init__(self):
        load_dotenv('.env')
        self.con = sqlite3.connect('db.db', check_same_thread=False)
        self.bot = DialogBot.get_secure_bot(
            os.environ.get('BOT_ENDPOINT'),
            grpc.ssl_channel_credentials(),
            os.environ.get('BOT_TOKEN')
        )
        self.bad = []
        self.bot.messaging.on_message_async(self.on_msg, self.on_click)
        while True:
            time.sleep(50)
            cur = self.con.cursor()
            users = cur.execute('SELECT * FROM users').fetchall()
            schedule = cur.execute('SELECT * FROM schedule').fetchall()
            current_time = int(time.time()) / 60
            for i in schedule:
                for e in users:
                    if int(i[3]) <= current_time - int(e[5]) / 60 <= int(i[3]) + 1:
                        question = self.get_question(str(i[1]), int(i[2]))
                        self.bot.messaging.send_message(
                            self.bot.users.get_user_peer_by_id(e[0]),
                            '\U0001F44B Привет!\n'
                            'Это автоматическое сообщение, в котором содержится важная для тебя информация '
                            '(по крайней мере, так подумали наши менеджеры).\n\n'
                            '*%s*\n'
                            '%s' % (str(question[1]), str(question[2]))
                        )
            cur.close()

    def on_msg(self, *params):
        user = self.get_user(params[0].sender_uid)
        message = str(params[0].message.textMessage.text)
        if user:
            state = user[3]
        else:
            self.create_user(params[0].sender_uid)
            state = 'menu'

        if message == '/start':
            self.set_state(user[0], 'menu')
            themes = self.get_themes()
            self.bot.messaging.send_message(
                params[0].peer,
                '\U0001F44B Привет!\n'
                'Я — бот, который поможет тебе освоиться в нашем дружном коллективе!\n'
                'Нажми на одну из тем, чтобы посмотреть подробную информацию по ней.',
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                i,
                                interactive_media.InteractiveMediaButton('view_theme_' + themes[i][0], themes[i][1]),
                                'primary'
                            ) for i in range(len(themes))
                        ]
                    ),
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                len(themes) + 1,
                                interactive_media.InteractiveMediaButton('themes_manager',
                                                                         'Панель управления базой знаний')
                            ),
                            interactive_media.InteractiveMedia(
                                len(themes) + 2,
                                interactive_media.InteractiveMediaButton('schedule_manager',
                                                                         'Менеджер отложенных сообщений')
                            ),
                            interactive_media.InteractiveMedia(
                                len(themes) + 2,
                                interactive_media.InteractiveMediaButton('make_notice',
                                                                         'Сделать объявление')
                            )
                        ]
                    )
                ]
            )
        elif state == 'add_theme':
            if len(message.strip().split()) >= 2:
                name = message.strip().split()[-1]
                label = ' '.join(message.strip().split()[:-1])
                if name not in [i[0] for i in self.get_themes()]:
                    self.add_theme(name, label)
                    themes = {}
                    for i in self.get_themes():
                        themes['theme_' + str(i[0])] = str(i[1])
                    self.bot.messaging.send_message(
                        self.bot.users.get_user_peer_by_id(user[0]),
                        '\U00002705 Тема *%s* создана.' % label,
                        [
                            interactive_media.InteractiveMediaGroup(
                                [
                                    interactive_media.InteractiveMedia(
                                        101,
                                        interactive_media.InteractiveMediaSelect(themes,
                                                                                 'Выбери тему для настройки')
                                    ),
                                    interactive_media.InteractiveMedia(
                                        102,
                                        interactive_media.InteractiveMediaButton('add_theme',
                                                                                 'Добавить тему'),
                                        'primary'
                                    ),
                                    interactive_media.InteractiveMedia(
                                        103,
                                        interactive_media.InteractiveMediaButton('back_to_menu',
                                                                                 'Назад в меню')
                                    )
                                ]
                            )
                        ]
                    )
                    self.set_state(user[0], 'menu')
                else:
                    self.bot.messaging.send_message(
                        self.bot.users.get_user_peer_by_id(user[0]),
                        'Такой идентификатор уже существует.\n'
                        'Попробуй еще раз, но с чем-то *уникальным.*'

                    )
            else:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Мне нужно несколько слов через пробел.\n'
                    'Попробуй еще раз.'
                )
        elif state.startswith('add_question_'):
            try:
                theme = state[13:]
                question, answer = message.strip().split('\n\n')
                self.add_question(theme, question, answer)
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    '\U00002705 Вопрос добавлен.',
                    [
                        interactive_media.InteractiveMediaGroup(
                            [
                                interactive_media.InteractiveMedia(
                                    114,
                                    interactive_media.InteractiveMediaButton('theme_%s' % theme,
                                                                             'К списку вопросов'),
                                    'primary'
                                )
                            ]
                        )
                    ]
                )
            except ValueError:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Я тебя не понял. Мне нужен вопрос и ответ именно в таком формате:\n'
                    'Вопрос\n\n'
                    'Ответ'
                )
        elif state.startswith('edit_question_'):
            question_id = state[14:].split('_')[0]
            theme = '_'.join(state[14:].split('_')[1:])
            try:
                question, answer = message.strip().split('\n\n')
                self.edit_question(theme, question_id, question, answer)
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    '\U00002705 Вопрос отредактирован.',
                    [
                        interactive_media.InteractiveMediaGroup(
                            [
                                interactive_media.InteractiveMedia(
                                    114,
                                    interactive_media.InteractiveMediaButton('theme_%s' % theme,
                                                                             'К списку вопросов'),
                                    'primary'
                                )
                            ]
                        )
                    ]
                )
            except ValueError:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Я тебя не понял. Мне нужен вопрос и ответ именно в таком формате:\n'
                    'Вопрос\n\n'
                    'Ответ'
                )

        elif state.startswith('theme_'):
            theme = state[6:]
            questions = self.get_questions(theme)
            questions_ids = [int(i[0]) for i in questions]
            try:
                question_id = int(message.strip())
                if question_id not in questions_ids:
                    raise ValueError
                else:
                    self.set_state(user[0], 'question_%s_%s' % (str(question_id), str(theme)))
                    question = questions[questions_ids.index(question_id)]
                    self.bot.messaging.send_message(
                        self.bot.users.get_user_peer_by_id(user[0]),
                        'Вопрос *%s*\n\n'
                        '%s' % (str(question[1]), str(question[2])),
                        [
                            interactive_media.InteractiveMediaGroup(
                                [
                                    interactive_media.InteractiveMedia(
                                        115,
                                        interactive_media.InteractiveMediaButton('edit_question_%s_%s' %
                                                                                 (str(question[0]), theme),
                                                                                 'Редактировать'),
                                        'primary'
                                    ),
                                    interactive_media.InteractiveMedia(
                                        116,
                                        interactive_media.InteractiveMediaButton('delete_question_%s_%s' %
                                                                                 (str(question[0]), theme),
                                                                                 'Удалить'),
                                        'danger'
                                    ),
                                    interactive_media.InteractiveMedia(
                                        117,
                                        interactive_media.InteractiveMediaButton('theme_%s' % theme,
                                                                                 'Назад')
                                    )
                                ]
                            )
                        ]
                    )
            except ValueError:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Кажется, нет вопроса с таким номером.'
                )
        elif state.startswith('view_theme_'):
            theme = state[11:]
            try:
                question_id = int(message.strip())
                answer = self.get_question(theme, question_id)
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    '*%s*\n\n'
                    '%s' % (str(answer[1]), str(answer[2])),
                    [
                        interactive_media.InteractiveMediaGroup(
                            [
                                interactive_media.InteractiveMedia(
                                    117,
                                    interactive_media.InteractiveMediaButton('view_theme_%s' % theme,
                                                                             'Назад')
                                )
                            ]
                        )
                    ]
                )
            except ValueError:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Кажется, нет вопроса с таким номером. Попробуй еще раз.'
                )
        elif state == 'make_notice':
            msg = message.strip()
            self.make_notice(user[0], msg)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                '\U00002705 Объявление успешно отправлено всем пользователям.'
            )
        elif state == 'delete_pending_msg':
            try:
                msg = int(message.strip())
                cur = self.con.cursor()
                schedule = cur.execute('SELECT * FROM schedule').fetchall()
                schedule_ids = [int(i[0]) for i in schedule]
                if msg not in schedule_ids:
                    self.bot.messaging.send_message(
                        self.bot.users.get_user_peer_by_id(user[0]),
                        'Сообщения с таким номером нет. Попробуй еще раз.'
                    )
                else:
                    self.delete_schedule(msg)
                    self.bot.messaging.send_message(
                        self.bot.users.get_user_peer_by_id(user[0]),
                        '\U00002705 Отложенное сообщение успешно удалено.',
                        [
                            interactive_media.InteractiveMediaGroup(
                                [
                                    interactive_media.InteractiveMedia(
                                        117,
                                        interactive_media.InteractiveMediaButton('schedule_manager',
                                                                                 'Назад в менеджер'),
                                        'primary'
                                    )
                                ]
                            )
                        ]
                    )
            except ValueError:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Сообщения с таким номером нет. Попробуй еще раз.'
                )
        elif state == 'add_pending_msg':
            try:
                question_id, theme, minutes = message.strip().split()
                self.add_schedule(theme, question_id, minutes)
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    '\U00002705 Отложенное сообщение создано.',
                    [
                        interactive_media.InteractiveMediaGroup(
                            [
                                interactive_media.InteractiveMedia(
                                    123,
                                    interactive_media.InteractiveMediaButton('schedule_manager',
                                                                             'Назад в менеджер'),
                                    'primary'
                                )
                            ]
                        )
                    ]
                )
            except ValueError:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Я тебя не понял. Пришли сообщение, соблюдая формат.',
                    [
                        interactive_media.InteractiveMediaGroup(
                            [
                                interactive_media.InteractiveMedia(
                                    124,
                                    interactive_media.InteractiveMediaButton('schedule_manager',
                                                                             'Отмена')
                                )
                            ]
                        )
                    ]
                )

    def on_click(self, *params):
        user = self.get_user(params[0].uid)
        value = params[0].value
        if value == 'themes_manager':
            self.set_state(user[0], 'themes_manager')
            themes = {}
            for i in self.get_themes():
                themes['theme_' + str(i[0])] = str(i[1])
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                '\U0001F916 Это панель управления.\n'
                'Здесь ты можешь управлять темами и вопросами, а также редактировать ответы на них.',
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                101,
                                interactive_media.InteractiveMediaSelect(themes,
                                                                         'Выбери тему для настройки')
                            ),
                            interactive_media.InteractiveMedia(
                                102,
                                interactive_media.InteractiveMediaButton('add_theme',
                                                                         'Добавить тему'),
                                'primary'
                            ),
                            interactive_media.InteractiveMedia(
                                103,
                                interactive_media.InteractiveMediaButton('back_to_menu',
                                                                         'Назад в меню')
                            )
                        ]
                    )
                ]
            )
        elif value == 'add_theme':
            self.set_state(user[0], 'add_theme')
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'Пришли мне название темы и ее сокращение на английском через пробел.\n'
                'Например: График работы schedule\n'
                '*График работы* станет названием, а *schedule* — уникальным идентификатором.'

            )
        elif value.startswith('theme_'):
            self.set_state(user[0], value)
            theme = value[6:]
            theme_label = [i[1] for i in self.get_themes() if i[0] == theme][0]
            questions = self.get_questions(theme)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'Вопросы в теме *%s*\n\n'
                '%s' % (theme_label,
                        '\n'.join([str(questions[i][0]) + '. ' + str(questions[i][1])
                                   for i in range(len(questions))])),
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                111,
                                interactive_media.InteractiveMediaButton('add_question_%s' % theme,
                                                                         'Добавить вопрос'),
                                'primary'
                            ),
                            interactive_media.InteractiveMedia(
                                112,
                                interactive_media.InteractiveMediaButton('delete_theme_%s' % theme,
                                                                         'Удалить тему'),
                                'danger'
                            ),
                            interactive_media.InteractiveMedia(
                                113,
                                interactive_media.InteractiveMediaButton('themes_manager',
                                                                         'Назад')
                            )
                        ]
                    )
                ]
            )
            if len(questions) > 0:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Пришли мне номер вопроса для его просмотра и редактирования.'
                )
        elif value.startswith('add_question_'):
            self.set_state(user[0], value)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                '*Добавление вопроса*\n'
                'Пришли через пустую строку вопрос и ответ на него.\n'
                'Например:\n'
                'Как подключиться к Wi-Fi?\n\n'
                'Для подключения к Wi-Fi введите пароль 12345678.'
            )
        elif value.startswith('delete_question_'):
            question_id = value[16:].split('_')[0]
            theme = '_'.join(value[16:].split('_')[1:])
            self.delete_question(theme, question_id)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                '\U00002705 Вопрос удален.',
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                115,
                                interactive_media.InteractiveMediaButton('theme_%s' % theme,
                                                                         'К списку вопросов'),
                                'primary'
                            )
                        ]
                    )
                ]
            )
        elif value.startswith('edit_question_'):
            question_id = value[14:].split('_')[0]
            theme = '_'.join(value[14:].split('_')[1:])
            self.set_state(user[0], value)
            self.set_state_info(user[0], json.dumps({'theme': theme, 'question_id': int(question_id)}))
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                '*Редактирование вопроса*\n'
                'Пришли через пустую строку новый вопрос и ответ.\n'
                'Например:\n'
                'Как подключиться к Wi-Fi?\n\n'
                'Для подключения к Wi-Fi введите пароль 12345678.',
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                115,
                                interactive_media.InteractiveMediaButton('theme_%s' % theme, 'Отмена')
                            )
                        ]
                    )
                ]
            )
        elif value == 'back_to_menu':
            self.set_state(user[0], 'menu')
            themes = self.get_themes()
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'Нажми на одну из тем, чтобы посмотреть подробную информацию по ней.',
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                i,
                                interactive_media.InteractiveMediaButton('view_theme_' + themes[i][0], themes[i][1]),
                                'primary'
                            ) for i in range(len(themes))
                        ]
                    ),
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                len(themes) + 1,
                                interactive_media.InteractiveMediaButton('themes_manager',
                                                                         'Панель управления базой знаний')
                            ),
                            interactive_media.InteractiveMedia(
                                len(themes) + 2,
                                interactive_media.InteractiveMediaButton('schedule_manager',
                                                                         'Менеджер отложенных сообщений')
                            ),
                            interactive_media.InteractiveMedia(
                                len(themes) + 2,
                                interactive_media.InteractiveMediaButton('make_notice',
                                                                         'Сделать объявление')
                            )
                        ]
                    )
                ]
            )
        elif value.startswith('view_theme_'):
            theme = value[11:]
            self.set_state(user[0], value)
            theme_label = [i[1] for i in self.get_themes() if i[0] == theme][0]
            questions = self.get_questions(theme)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'Тема *%s*\n\n'
                '%s' % (theme_label,
                        '\n'.join([str(questions[i][0]) + '. ' + str(questions[i][1])
                                   for i in range(len(questions))])),
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                103,
                                interactive_media.InteractiveMediaButton('back_to_menu',
                                                                         'Назад в меню')
                            )
                        ]
                    )
                ]
            )
            if len(questions) > 0:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(user[0]),
                    'Пришли мне номер вопроса, чтобы узнать ответ на него.'
                )
        elif value.startswith('delete_theme_'):
            theme = value[13:]
            self.delete_theme(theme)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                '\U00002705 Тема *%s* удалена.' % theme,
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                117,
                                interactive_media.InteractiveMediaButton('themes_manager',
                                                                         'Назад в панель управления')
                            )
                        ]
                    )
                ]
            )
        elif value == 'schedule_manager':
            cur = self.con.cursor()
            schedule = cur.execute('SELECT * FROM schedule').fetchall()
            themes = {}
            for i in self.get_themes():
                themes[str(i[0])] = str(i[1])
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                '*Отложенные сообщения*\n\n'
                '%s' % '\n'.join([str(i[0]) + '. Гайд №' + str(i[2]) + ' из темы ' + themes[str(i[1])] +
                                  ' (через ' + str(i[3]) + ' мин)' for i in schedule]),
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                121,
                                interactive_media.InteractiveMediaButton('add_pending_msg',
                                                                         'Добавить отложенное сообщение'),
                                'primary'
                            ),
                            interactive_media.InteractiveMedia(
                                122,
                                interactive_media.InteractiveMediaButton('delete_pending_msg',
                                                                         'Удалить отложенное сообщение'),
                                'danger'
                            ),
                            interactive_media.InteractiveMedia(
                                120,
                                interactive_media.InteractiveMediaButton('back_to_menu',
                                                                         'Назад')
                            )
                        ]
                    )
                ]
            )
        elif value == 'make_notice':
            self.set_state(user[0], value)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'Пришли мне текст уведомления.\n'
                'Оно будет мгновенно отправлено всем пользователям бота.',
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                118,
                                interactive_media.InteractiveMediaButton('back_to_menu',
                                                                         'Отмена'),
                                'primary'
                            )
                        ]
                    )
                ]
            )
        elif value == 'delete_pending_msg':
            self.set_state(user[0], value)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'Пришли мне номер сообщения, которое необходимо удалить.',
                [
                    interactive_media.InteractiveMediaGroup(
                        [
                            interactive_media.InteractiveMedia(
                                122,
                                interactive_media.InteractiveMediaButton('schedule_manager',
                                                                         'Назад')
                            )
                        ]
                    )
                ]
            )
        elif value == 'add_pending_msg':
            self.set_state(user[0], value)
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'Пришли мне через пробел номер гайда, идентификатор темы и время *в минутах*'
                'после регистрации пользователя,'
                'через которое придет сообщение.\n\n'
                'Например: 1 office 13\n'
                'Гайд №1 из темы с идентификатором office придет через 13 минут после регистрации пользователя.',
            )
            self.bot.messaging.send_message(
                self.bot.users.get_user_peer_by_id(user[0]),
                'На всякий случай держи названия тем:\n'
                '%s' % '\n'.join([str(i[1]) + ' — ' + str(i[0]) for i in self.get_themes()])
            )

    def get_user(self, uid):
        cur = self.con.cursor()
        user = cur.execute('SELECT * FROM users WHERE id = ? LIMIT 1', (int(uid),)).fetchone()
        if not user:
            username = str(self.bot.users.get_user_by_id(uid).data.nick.value)
            self.create_user(uid, username=username, role='user')
            self.con.commit()
            user = cur.execute('SELECT * FROM users WHERE id = ? LIMIT 1', (int(uid),)).fetchone()
        cur.close()
        return user if user else None

    def create_user(self, uid, username='', role='user'):
        cur = self.con.cursor()
        cur.execute(
            'INSERT INTO users(id, username, role, state, state_info, reg_time) VALUES (?, ?, ?, "menu", "", ?);',
            (int(uid), str(username), str(role), int(time.time())))
        self.con.commit()
        cur.close()
        return True

    def set_state(self, uid, state):
        cur = self.con.cursor()
        cur.execute('UPDATE users SET state = ? WHERE id = ?', (str(state), int(uid)))
        self.con.commit()
        cur.close()
        return True

    def set_state_info(self, uid, state_info):
        cur = self.con.cursor()
        cur.execute('UPDATE users SET state_info = ? WHERE id = ?', (str(state_info).replace("'", '"'), int(uid)))
        self.con.commit()
        cur.close()
        return True

    def get_themes(self):
        cur = self.con.cursor()
        themes = cur.execute('SELECT * FROM themes').fetchall()
        cur.close()
        return themes

    def add_theme(self, name, label):
        cur = self.con.cursor()
        cur.execute('INSERT INTO themes (name, label) VALUES (?, ?)', (str(name), str(label)))
        cur.execute('CREATE TABLE theme_%s (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT)' % name)
        self.con.commit()
        cur.close()
        return True

    def delete_theme(self, theme):
        cur = self.con.cursor()
        cur.execute('DELETE FROM themes WHERE name = ?', (str(theme),))
        cur.execute('DROP TABLE theme_%s' % str(theme))
        self.con.commit()
        cur.close()
        return True

    def get_questions(self, theme):
        cur = self.con.cursor()
        themes = cur.execute('SELECT * FROM theme_%s' % theme).fetchall()
        cur.close()
        return themes

    def get_question(self, theme, question_id):
        cur = self.con.cursor()
        question = cur.execute('SELECT * FROM theme_%s WHERE id = ?' % theme, (str(question_id),)).fetchone()
        cur.close()
        return question

    def edit_question(self, theme, question_id, question, answer):
        cur = self.con.cursor()
        cur.execute('UPDATE theme_%s SET question = ? WHERE id = ?' % theme, (str(question), str(question_id)))
        cur.execute('UPDATE theme_%s SET answer = ? WHERE id = ?' % theme, (str(answer), str(question_id)))
        self.con.commit()
        cur.close()
        return True

    def add_question(self, theme, question, answer):
        cur = self.con.cursor()
        cur.execute('INSERT INTO theme_%s (question, answer) VALUES (?, ?)' % theme, (str(question), str(answer)))
        self.con.commit()
        cur.close()
        return True

    def delete_question(self, theme, question_id):
        cur = self.con.cursor()
        cur.execute('DELETE FROM theme_%s WHERE id = ?' % theme, (str(question_id),))
        self.con.commit()
        cur.close()
        return True

    def get_schedule(self):
        cur = self.con.cursor()
        schedule = cur.execute('SELECT * FROM schedule')
        cur.close()
        return schedule

    def delete_schedule(self, msg):
        cur = self.con.cursor()
        schedule = cur.execute('DELETE FROM schedule WHERE id = ?', (str(msg),))
        self.con.commit()
        cur.close()
        return True

    def add_schedule(self, theme, question_id, minutes):
        cur = self.con.cursor()
        cur.execute('INSERT INTO schedule (theme, question_id, time) VALUES (?, ?, ?)', (str(theme), str(question_id),
                                                                                         str(minutes)))
        self.con.commit()
        cur.close()
        return True

    def make_notice(self, uid, msg):
        cur = self.con.cursor()
        users = cur.execute('SELECT * FROM users').fetchall()
        for e in users:
            if int(e[0]) != uid:
                self.bot.messaging.send_message(
                    self.bot.users.get_user_peer_by_id(e[0]),
                    '\U000026A0 *Объявление от %s :*\n\n'
                    '%s' % ('@' + str(self.get_user(uid)[1]), str(msg))
                )
        cur.close()
        return True


bot = Bot()
