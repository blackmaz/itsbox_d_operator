# Operator for ItsBox Designer

ItsBox Designer의 Operation 모듈이다.
Communicator로부터 처리 또는 관리목적의 메시지를 전달받아 처리하는 모듈이다.



###1. 설치
   * 임의의 위치에 프로젝트 전체파일 및 디렉토리 복사
   * Python 모듈 설치(pip install 모듈명)
     * tornado
     * psutil
     * pika
     * future
     * futures
     * apache-libcloud, saltstack
   * MessageQueue 설치 및 계정생성(현재는 RabbitMQ만 지원)
   

###2. 환경설정 
   * 파일 위치 : `{PROJECT_HOME}/itsbox/operator/Config.py` 
   * 항목 설명 :
     * PROJECT_NAME, PROJECT_DIR : 로그위치를 프로젝트 하위로 지정하기 위한 변수(변경 불필요)
     * LOG_LEVEL : 로그 레벨(NOTSET < CRITICAL < ERROR < WARNING < INFO < DEBUG)
     * LOG_FILE_DIR : 로그파일이 위치할 디렉토리 경로(상대경로 가능)
     * LOG_FILE_PREFIX : 로그파일 이름(접두사)를 포함한 디렉토리 경로
     * LOG_FILE_ROTATION : 로그파일 로테이션 여부(True or False)
     * LOG_FILE_MAX_BYTES : 로그파일 로테이션 시 파일의 최대 크기
     * LOG_FILE_MAX_COUNT : 로그파일 로테이션 시 파일의 최대 개수(이것보다 많아질 경우 가장 오래된 파일이 삭제됨)
     * LOG_FILE_ALLINONE : 모든 로그를 하나의 파일로 기록 여부(True or False)
     
     * RABBITMQ_IP, RABBITMQ_PORT : RabbitMQ 접속 정보(IP, Port)
     * RABBITMQ_VHOST : RabbitMQ 가상호스트 경로
     * RABBITMQ_USER, RABBITMQ_PASS : RabbitMQ 계정 정보(Queue의 Read/Write가 가능한 계정)
     * RABBITMQ_QNAME_MGR_IN, RABBITMQ_QNAME_MGR_OUT : 관리 메시지를 위한 Inbound/Outbound Queue 이름
     * RABBITMQ_QNAME_MSG_IN, RABBITMQ_QNAME_MSG_OUT : 처리 메시지를 위한 Inbound/Outbound Queue 이름
     
     * MAX_WORKER_PER_NODE : 노드당 기동될 수 있는 Worker 프로세스의 최대 개수
     * MAX_THREAD_PER_WORKER : Worker 프로세스 당 기동될 수 있는 Thread의 최대 개수
     * WORKER_COUNT : 기동할 Worker 프로세스 개수
     * THREAD_COUNT : Worker 프로세스 당 기동할 Thread 개수
     * WORKER_WATCHER_INTERVAL : Manager가 Worker 프로세스를 감시하는 주기(초)
     * MANAGER_REQUEST_TIMEOUT_PER_WORKER : Manager가 Worker 프로세스 상태 정보를 요청하는 Timeout(초)  

     * WEBSOCKET_MGMT_SERVER_BOOT : Operator 관리를 위한 Websocket 서버 기동여부
     * WEBSOCKET_MGMT_SERVER_PORT : 관리서버 Websocket Listen Port
     
     * RULE_MODULE_BASE : Rule 호출을 위한 모듈의 위치(변경 불필요)
   
   
###3. 기동/종료
   * 최상위 디렉토리에서 아래의 파일을 수행
     * 기동     : `start_operator.sh(bat)`
     * 정상종료 : `stop_operator.sh(bat)`
     * 강제종료 : `kill_operator.sh(bat)`


###4. 동작 및 테스트
   * ItsBox Designer Communicator를 통해 Queue로 전문을 전달해야 함

   * 테스트를 위해 Message Queue에 전문을 직접 전송하여 기능을 확인할 수 있음
   * Communicator 및 Operator 테스트 페이지를 제공함
     * test 디렉토리 하위의 `itsbox_d_server_test.html` 파일을 브라우저로 수행

   * Operator가 전문을 처리하기 위해서는 아래와 같이 입력되어야 함
     * 공통항목 :
       * time : Unix(Epoch) Time
       * direction : 1(Inbound)
       * location : 2(Operator)
     * Task 관련 항목 : 
       * op_code : 수행할 Module, Class, Function (key/value 형식)
       * op_data : 전달할 인자값 (배열 형식)
     * Management 관련 항목
       * op_action : 수행할 Action
       * op_target : Action을 수행할 대상
       * op_detail : 추가 옵션
     * 응답항목 :
       * success : 1(success) or 2(fail)
       * msg : 응답 메시지
   
   * Task 전문
     * (itsbox.operator.)test.module내 TestClass.callme() 호출 예시:  
       `{ 
         "time" : "123456789",
	     "client_channel_id" : "ABCD1234",
	     "company_code" : "1",
	     "location" : "2",
	     "direction" : "1",
	     "op_code" : {"module":"test.module", "class":"TestClass", "fuction":"callme"}
	     "op_data" : {"arg1":"argument1", "arg2":"argument2"}
       }`
     
   * Management 전문
     * Operator 전체 종료 예시:  
       `{
         "time" : "123456789",
         "location" : "2",
         "direction": "1",
         "op_action" : "stop",
         "op_target" : "all",
         "op_detail" : ""
       }`
     * Worker 프로세스 3개를 40개 Thread로 기동 예시:  
       `{
         "time" : "123456789",
         "location" : "2",
         "direction": "1",
         "op_action" : "start",
         "op_target" : "worker",
         "op_detail" : "3(40)"
       }`     
     * Worker의 상태정보 조회 예시:  
       `{
         "time" : "123456789",
         "location" : "2",
         "direction": "1",
         "op_action" : "info",
         "op_target" : "worker",
         "op_detail" : "all"
       }`


###5. 로그
   * 로그 디렉토리는 환경파일의 LOG_FILE_DIR 항목에서 지정한 위치에 기록됨
   * 기본위치: `{PROJECT_HOME}/logs`
   
   * 로그 파일은 Engine, Access, Error 로그로 분류됨
     * Engine 로그 형식 :  
     `[날짜 시간] [로그레벨] [로거명] [PID] [Thread명] [Function명(파일명:라인수)] 메시지`
     * Access 로그 형식 : 
     `[날짜 시간] [메시지구분] 회사코드 클라이언트채널ID "모듈:클래스:Function" 성공여부 회신여부 요청크기 응답크기 응답시간(초)`
     * Error 로그 형식 : 
     `[날짜 시간] [로그레벨] [로거명] [PID] [Thread명] [Function명(파일명:라인수)] 메시지 {NEWLINE} 스택트레이스`


###6. 제거
   * 임의의 위치에 복사한 프로젝트 디렉토리 삭제

