import { NextRequest, NextResponse } from 'next/server';
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export async function POST(req: NextRequest) {
  try {
    const { messages } = await req.json();

    const mcpBaseUrl = process.env.MCP_SERVER_URL; 
    const mcpToken = process.env.MCP_AUTH_TOKEN;

  
    const tools: OpenAI.ChatCompletionTool[] = [
      {
        type: 'function',
        function: {
          name: 'list_review_sources',
          description: '리뷰 수집 출처 목록, 데이터 개수, 날짜 범위 및 수집 시간을 조회합니다.',
          parameters: { type: 'object', properties: {} },
        },
      },
      {
        type: 'function',
        function: {
          name: 'get_latest_reviews',
          description: '특정 사이트의 가장 최신 리뷰 데이터를 조회합니다.',
          parameters: {
            type: 'object',
            properties: {
              site: {
                type: 'string',
                enum: ['kakao', 'tripadvisor', 'tripdotcom'],
                description: '리뷰 수집 출처 사이트 (기본값: kakao)',
              },
              limit: { type: 'number', description: '조회할 리뷰 개수 (1~50, 기본값: 10)' },
            },
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'search_reviews',
          description: '키워드, 날짜, 별점 등으로 리뷰를 검색합니다.',
          parameters: {
            type: 'object',
            properties: {
              site: { type: 'string', enum: ['kakao', 'tripadvisor', 'tripdotcom'] },
              keyword: { type: 'string', description: '검색할 키워드' },
              start_date: { type: 'string', description: '시작 날짜 (YYYY-MM-DD)' },
              end_date: { type: 'string', description: '종료 날짜 (YYYY-MM-DD)' },
              min_rating: { type: 'number', description: '최소 평점 (1~5)' },
              max_rating: { type: 'number', description: '최대 평점 (1~5)' },
              limit: { type: 'number', description: '조회 개수 (1~100, 기본값: 20)' },
            },
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'aggregate_review_stats',
          description: '월/연도/요일별 리뷰 수, 평균 평점, 긍정/부정 비율 통계를 집계합니다.',
          parameters: {
            type: 'object',
            properties: {
              site: { type: 'string', enum: ['kakao', 'tripadvisor', 'tripdotcom'] },
              group_by: {
                type: 'string',
                enum: ['month', 'year', 'weekday'],
                description: '집계 기준 (month, year, weekday 중 선택)',
              },
              start_date: { type: 'string', description: '시작 날짜 (YYYY-MM-DD)' },
              end_date: { type: 'string', description: '종료 날짜 (YYYY-MM-DD)' },
            },
          },
        },
      },
      {
        type: 'function',
        function: {
          name: 'get_top_review_keywords',
          description: '리뷰에서 가장 많이 언급된 주요 키워드와 빈도수를 조회합니다.',
          parameters: {
            type: 'object',
            properties: {
              site: { type: 'string', enum: ['kakao', 'tripadvisor', 'tripdotcom'] },
              limit: { type: 'number', description: '상위 키워드 개수 (1~30, 기본값: 10)' },
            },
          },
        },
      },
    ];

    // 2. 1차 LLM 질의 (사용자 질문 분석 및 Tool 호출 판단)
    const firstResponse = await openai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages,
      tools,
      tool_choice: 'auto',
    });

    const responseMessage = firstResponse.choices[0].message;

    // 3. LLM이 MCP Tool 호출을 결정한 경우
    if (responseMessage.tool_calls && responseMessage.tool_calls.length > 0) {
      const toolCall = responseMessage.tool_calls[0];
      const functionName = toolCall.function.name;
      const functionArgs = JSON.parse(toolCall.function.arguments);

      // MCP 서버 (Starlette /mcp 엔드포인트)에 JSON-RPC 규격으로 요청 전송
      const endpoint = `${mcpBaseUrl?.replace(/\/$/, '')}/mcp`;
      
      const mcpHeaders: Record<string, string> = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };
      if (mcpToken) {
        mcpHeaders['Authorization'] = `Bearer ${mcpToken}`;
      }

      const mcpResponse = await fetch(endpoint, {
        method: 'POST',
        headers: mcpHeaders,
        body: JSON.stringify({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: {
            name: functionName,
            arguments: functionArgs,
          },
          id: 1,
        }),
      });

      const mcpResult = await mcpResponse.json();

      // 4. MCP 조회 결과를 대화 문맥에 포함시켜 2차 LLM 질의 (최종 답변 생성)
      const secondResponse = await openai.chat.completions.create({
        model: 'gpt-4o-mini',
        messages: [
          ...messages,
          responseMessage,
          {
            role: 'tool',
            tool_call_id: toolCall.id,
            content: JSON.stringify(mcpResult.result || mcpResult),
          },
        ],
      });

      return NextResponse.json({
        result: secondResponse.choices[0].message.content,
        toolUsed: functionName,
      });
    }

    // Tool 호출이 필요 없는 일상 대화인 경우
    return NextResponse.json({
      result: responseMessage.content,
    });

  } catch (error: any) {
    console.error('Agent Routing Error:', error);
    return NextResponse.json(
      { error: 'Agent 처리 과정에서 에러가 발생했습니다.', details: error.message },
      { status: 500 }
    );
  }
}