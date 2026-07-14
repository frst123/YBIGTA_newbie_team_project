from app.user.user_repository import UserRepository
from app.user.user_schema import User, UserLogin, UserUpdate


class UserService:
    def __init__(self, userRepoitory: UserRepository) -> None:
        self.repo = userRepoitory

    def login(self, user_login: UserLogin) -> User:
        ## TODO
        '''
        user login 기능 구현

        repo 객체의 email로 유저 찾기

        이메일 없음 -> 에러메시지 반환
        비밀번호 틀림 -> 에러메시지 반환
        else: 로그인 성공
        '''
        user = self.repo.get_user_by_email(user_login.email)

        if user is None:
            raise ValueError("User not Found.")
        
        if user.password != user_login.password:
            raise ValueError('Invalid ID/PW')

        return user # 통과 -> 유저 반환
        
    def register_user(self, new_user: User) -> User:
        ## TODO

        '''
        user register 기능 구현

        repo 객체의 email로 등록할 유저 찾기

        이메일 존재함 -> 이미 등록된 유저 -> 에러메시지 반환
        else: 신규유저 등록
        '''

        # Error 메시지 Status 조건이 '이메일'임..
        existing = self.repo.get_user_by_email(new_user.email)

        if existing is not None: # 이미 있으면 에러
            raise ValueError('User already Exists.')
        
        return self.repo.save_user(new_user)
        

    def delete_user(self, email: str) -> User:
        ## TODO
        '''
        user 삭제 기능 구현

        repo 객체의 email로 삭제할 유저 찾기

        이메일 없음 -> 존재하지 않는 유저 -> 에러메시지 반환
        else: 기존유저 삭제
        '''

        # Error 메시지 Status 조건이 '이메일'임..
        deleted_user = self.repo.get_user_by_email(email)

        ## 이메일 찾을수 없는 경우?
        if deleted_user is None:
            raise ValueError('User not Found.')

        else:
            self.repo.delete_user(deleted_user)

        return deleted_user

    def update_user_pwd(self, user_update: UserUpdate) -> User:
        ## TODO
        '''
        user password update 기능 구현

        repo 객체의 email로 업데이트할 유저 찾기

        이메일 없음 -> 존재하지 않는 유저 -> 에러메시지 반환
        else: 패스워드 업데이트 후 저장
        '''
        updated_user = self.repo.get_user_by_email(user_update.email)

        # 없으면 에러, 있으면 pwd 바꿔서 저장
        if updated_user is None:
            raise ValueError('User not Found.')
        
        else:
            updated_user.password = user_update.new_password
            self.repo.save_user(updated_user)

        return updated_user
        