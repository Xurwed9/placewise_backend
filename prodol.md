Продолжаем проверку Placewise API с места остановки.

Проект: /home/xurshed/Desktop/zazatech/placewise_backend
Base URL: http://127.0.0.1:8000
Swagger: http://127.0.0.1:8000/api/docs/

Не начинай проверку с начала.

Уже проверено:
- Public API: categories, home, places, фильтры/пагинация, place detail, reviews GET, similar, map, search suggest.
- Негативные проверки public API: 400/404, без токена 200, с просроченным токеном 401.
- Auth: send-code, verify, refresh.
- Profile: GET/PATCH /me/.
- Admin login и GET /admin/users/.
- Создан тестовый пользователь id=2, +992900123456, имя Swagger Test, роль user.
- Создан модератор id=10, +992900000011, роль moderator.

По состоянию на последнюю проверку:
- admin +992900000012 ещё не создан;
- тестовый пользователь для block/unblock +992900000013 ещё не создан;
- superuser: id=1, +992111111111;
- категорий 11, опубликованный place: test-cafe.

Незакрытые хвосты Admin Users:
- проверить ограничения роли admin;
- set-password на модераторе id=10;
- block/unblock на одноразовом пользователе;
- проверить, что user/moderator не получают лишние права.

Ближайший этап после хвостов: Admin Categories — GET списка и категории id=1, POST create, PATCH, DELETE одноразовой категории.

Новый superuser-токен я уже получил через admin login и вставил в Swagger Authorize.
Продолжай шаг за шагом: объясняй request body, response body и ожидаемые статусы.


refresh token
+992900123456
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc5NTU4OTI2MSwiaWF0IjoxNzkyOTk3MjYxLCJqdGkiOiJmMGNmZWNkZDNlNGU0MTk5YTU5MjAyODM5YWJmMzg3OCIsInVzZXJfaWQiOiIyIn0.MNEM1O4E_T63Do73a8siF-BR9Aq9HklsRZGduUVgsUk



refresh token
+992000000003
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc5NTU5MDAyMywiaWF0IjoxNzkyOTk4MDIzLCJqdGkiOiIwMzI1M2E2N2U0Yzk0ODM5OTEyZTQ2YjAzZGUxOWRjMiIsInVzZXJfaWQiOiIzIn0.jCg66nA2l73X8cjtgqrTWBWHQsO66WKjLArk5Lrgo6c


refresh token
+992900987654
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc5NTU5MjU2MSwiaWF0IjoxNzkzMDAwNTYxLCJqdGkiOiIxYTEyOGFkMGQzODI0YWI2YTUyYTlmMmFmMTcwZGZhOCIsInVzZXJfaWQiOiI0In0.jYHULonrLNxxbbJqQDHNBJeyov8ttr74yMFUpdz7yrc