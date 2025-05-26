from typing import Optional

from django.utils import timezone
from django.conf import settings # Google Client ID를 사용하기 위해 추가

from apps.account.domain.repositories import UserAccountRepository
from apps.account.domain.aggregates.user_account import UserAccount
from apps.account.domain.value_objects.email import Email
from apps.account.domain.value_objects.nickname import NickName
from apps.account.domain.value_objects.social_link import SocialLink
from .dtos import UserAccountDto, UpdateNicknameRequestDto, UserSocialLinkDto, AuthResponseDto, SocialLoginRequestDto # SocialLoginRequestDto 추가
from apps.account.infrastructure.token_services import TokenService
from apps.account.models import Users # Django User 모델
# from rest_framework_simplejwt.tokens import RefreshToken # TokenService가 처리하므로 직접 사용 안 함
from rest_framework_simplejwt.exceptions import TokenError
from google.oauth2 import id_token as google_id_token_verifier
from google.auth.transport import requests as google_auth_requests
# import logging # 로깅을 사용한다면 추가
# logger = logging.getLogger(__name__)

class UserAuthAppService:
    def __init__(self, user_account_repository: UserAccountRepository, token_service: TokenService):
        self.user_account_repository = user_account_repository
        self.token_service = token_service

    def _map_domain_to_dto(self, user_account: UserAccount) -> UserAccountDto:
        social_links_dto = [
            UserSocialLinkDto(provider_name=social_link.provider_name, social_id=social_link.social_id)
            for social_link in user_account.social_links
        ]
        return UserAccountDto(
            account_id=user_account.account_id,
            email=user_account.email.address,
            nickname=user_account.nickname.name,
            social_links=social_links_dto,
            created_at=user_account.created_at,
            last_login_at=user_account.last_login_at
        )

    def login_or_register_with_google(self, request_dto: SocialLoginRequestDto) -> AuthResponseDto:
        # [수정] Google ID 토큰 검증 로직 추가
        received_google_id_token = request_dto.id_token
        try:
            client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
            if not client_id:
                # logger.error("Google Client ID is not configured in settings.") # 로깅 예시
                raise ValueError("Google Client ID가 서버에 설정되지 않았습니다.")

            id_info = google_id_token_verifier.verify_oauth2_token(
                received_google_id_token,
                google_auth_requests.Request(), # HTTP 요청을 위한 transport 객체
                client_id # [필수] Audience 검증을 위해 settings.py에 설정된 Client ID 전달
            )

            # 검증된 정보 추출
            verified_google_user_id = id_info.get('sub') # Google 사용자의 고유 ID
            verified_email = id_info.get('email')        # Google 계정 이메일
            # is_email_verified = id_info.get('email_verified') # 이메일 검증 여부
            name_from_google = id_info.get('name')     # Google 계정 전체 이름
            # profile_picture_url_from_google = id_info.get('picture') # 프로필 사진 URL

            if not verified_google_user_id or not verified_email:
                raise ValueError("Google 토큰에서 필수 사용자 정보를 얻을 수 없습니다 (sub 또는 email 누락).")
            
            # (선택 사항) 요청으로 받은 이메일과 토큰에서 나온 이메일이 같은지 확인
            # if request_dto.email.lower() != verified_email.lower():
            #     raise ValueError("요청된 이메일과 Google 토큰의 이메일이 일치하지 않습니다.")

        except ValueError as e:
            # logger.warning(f"Google ID token verification failed: {str(e)}") # 로깅 예시
            raise ValueError(f"Google ID 토큰 검증 실패: {str(e)}")
        except Exception as e: # 예상치 못한 다른 오류 (네트워크 문제 등)
            # logger.error(f"Unexpected error during Google token verification: {str(e)}") # 로깅 예시
            raise Exception(f"Google 토큰 처리 중 예상치 못한 오류 발생: {str(e)}")

        # [수정] 검증된 Google 사용자 정보 사용
        social_link_vo = SocialLink(provider_name="google", social_id=verified_google_user_id)
        email_vo = Email(verified_email) # Google에서 검증된 이메일 사용

        existing_account_domain = self.user_account_repository.find_by_social_link(social_link_vo)
        is_new_user = False
        user_account_domain: UserAccount # 타입 힌트

        current_time = timezone.now()

        if existing_account_domain:
            user_account_domain = existing_account_domain
            user_account_domain.record_login(current_time) # 로그인 시간 업데이트
            # (선택) Google에서 받은 이메일이 기존 이메일과 다르면 업데이트할지 정책 결정
            if user_account_domain.email != email_vo:
                 # 실제로는 이메일 변경 시 추가적인 검증 절차가 필요할 수 있습니다.
                user_account_domain._email = email_vo # 도메인 객체의 이메일 업데이트
        else:
            # 신규 사용자 처리
            is_new_user = True
            
            # 닉네임 결정: 요청 DTO의 제안 -> Google 이름 -> 이메일 앞부분 순으로 사용
            nickname_str = request_dto.nickname_suggestion or name_from_google or verified_email.split('@')[0]
            suggested_nickname_vo = NickName(nickname_str)

            # 닉네임 중복 검사 (신규 사용자에 대해서만)
            if self.user_account_repository.find_by_nickname(suggested_nickname_vo):
                raise ValueError(f"닉네임 '{suggested_nickname_vo.name}'은 이미 사용 중이거나 형식에 맞지 않습니다. 다른 닉네임을 사용해주세요.")
            
            # (선택) 이메일 중복 검사: 다른 방식으로 이미 가입된 이메일인지 확인
            existing_user_by_email = self.user_account_repository.find_by_email(email_vo)
            if existing_user_by_email:
                # 이 경우, 해당 이메일의 기존 계정에 현재 Google 소셜 링크를 추가할지,
                # 아니면 오류로 처리할지 정책 결정 필요.
                # 여기서는 기존 계정에 소셜 링크를 추가하는 방향으로 가정 (Repository에서 처리)
                # 또는, raise ValueError(f"이메일 '{email_vo.address}'은 이미 다른 계정으로 사용 중입니다...")
                user_account_domain = existing_user_by_email # 기존 계정을 가져와서
                user_account_domain.add_social_link(social_link_vo) # 소셜 링크 추가 (도메인 객체에 이런 메소드가 있다고 가정)
                is_new_user = False # 엄밀히 말하면 새 유저는 아니지만, 새 소셜 연동임
            else:
                # 완전 신규 사용자
                temp_account_id_for_new_user = 0 # 저장 시 실제 ID 할당됨
                user_account_domain = UserAccount(
                    account_id=temp_account_id_for_new_user,
                    email=email_vo,
                    nickname=suggested_nickname_vo,
                    social_links=[social_link_vo], # 초기 소셜 링크
                    created_at=current_time,
                    last_login_at=current_time,
                    # profile_picture_url = profile_picture_url_from_google # UserAccount 도메인 객체가 이를 관리한다면
                )

        # UserAccountRepository의 save 메소드가 Users 모델과 UserSocialAccounts 모델을 함께 처리해야 함
        saved_user_account_domain = self.user_account_repository.save(user_account_domain)

        # Django User 모델 인스턴스 가져오기 (토큰 발급용)
        try:
            # UserAccountRepository.save()가 반환하는 domain 객체의 account_id는 Django Users 모델의 id와 일치해야 함
            user_model_instance = Users.objects.get(id=saved_user_account_domain.account_id)
        except Users.DoesNotExist:
            # logger.critical(f"User model not found for account_id: {saved_user_account_domain.account_id} after save.") # 로깅
            raise Exception("계정 저장 후 Django 사용자 모델을 찾을 수 없습니다.")

        # JWT 토큰 발급 (TokenService 사용)
        tokens = self.token_service.create_token_for_user(user_model_instance)
        access_token = tokens['access']
        refresh_token = tokens['refresh']

        # 응답 DTO 생성
        user_dto = self._map_domain_to_dto(saved_user_account_domain)
        return AuthResponseDto(access_token=access_token, refresh_token=refresh_token, user=user_dto, is_new_user=is_new_user)

    def logout_user(self, request_dto): # request_dto 타입을 명시하면 좋음 (예: LogoutRequestDto)
        try:
            refresh_token_str = request_dto.refresh_token
            # self.token_service.blacklist_token(refresh_token_str) # TokenService에 위임 가능
            # 또는 직접 simplejwt의 RefreshToken 사용
            token = RefreshToken(refresh_token_str)
            token.blacklist()
        except TokenError as e:
            # logger.info(f"Token blacklist error during logout (token might be already blacklisted or invalid): {str(e)}")
            pass 
        except Exception as e:
            # logger.error(f"Unexpected error during logout: {str(e)}")
            raise Exception(f"로그아웃 처리 중 예기치 않은 오류 발생: {str(e)}")



class UserProfileAppService:
    def __init__(self, user_account_repository: UserAccountRepository):
        self.user_account_repository = user_account_repository

    def _map_domain_to_dto(self, user_account: UserAccount) -> UserAccountDto:
        social_links_dto = [
            UserSocialLinkDto(provider_name=social_link.provider_name, social_id=social_link.social_id)
            for social_link in user_account.social_links
        ]
        return UserAccountDto(
            account_id=user_account.account_id,
            email=user_account.email.address,
            nickname=user_account.nickname.name,
            social_links=social_links_dto,
            created_at=user_account.created_at,
            last_login_at=user_account.last_login_at
        )

    def get_user_profile(self, account_id: int) -> Optional[UserAccountDto]:
        user_account_domain = self.user_account_repository.find_by_id(account_id)
        if not user_account_domain:
            return None
        return self._map_domain_to_dto(user_account_domain)

    def update_user_nickname(self, account_id: int, request_dto: UpdateNicknameRequestDto) -> UserAccountDto:
        user_account_domain = self.user_account_repository.find_by_id(account_id)
        if not user_account_domain:
            raise ValueError("사용자를 찾을 수 없습니다.")

        new_nickname_vo = NickName(request_dto.nickname)

        def nickname_uniqueness_checker(nickname_to_check: NickName, current_account_id: int):
            existing_user = self.user_account_repository.find_by_nickname(nickname_to_check)
            return not (existing_user and existing_user.account_id != current_account_id)

        user_account_domain.update_nickname(new_nickname_vo, nickname_uniqueness_checker)

        updated_user_account_domain = self.user_account_repository.save(user_account_domain)
        return self._map_domain_to_dto(updated_user_account_domain)


class UserAccountDeactivationAppService:
    def __init__(self, user_account_repository: UserAccountRepository):
        self.user_account_repository = user_account_repository

    def deactivate_account(self, account_id: int) -> None:
        # UserAccountRepository.delete()가 실제로는 is_active=False로 처리하거나
        # 관련 데이터를 익명화하는 등의 로직을 수행해야 할 수 있음
        self.user_account_repository.delete(account_id)