# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: pogoprotos/networking/game/gamegmtemplates/game_gm_templates_action_request.proto

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from pogoprotos.networking.game.gamegmtemplates import game_gm_templates_action_pb2 as pogoprotos_dot_networking_dot_game_dot_gamegmtemplates_dot_game__gm__templates__action__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='pogoprotos/networking/game/gamegmtemplates/game_gm_templates_action_request.proto',
  package='pogoprotos.networking.game.gamegmtemplates',
  syntax='proto3',
  serialized_options=None,
  serialized_pb=b'\nQpogoprotos/networking/game/gamegmtemplates/game_gm_templates_action_request.proto\x12*pogoprotos.networking.game.gamegmtemplates\x1aIpogoprotos/networking/game/gamegmtemplates/game_gm_templates_action.proto\"\x90\x01\n\x1cGameGmTemplatesActionRequest\x12W\n\x0crequest_type\x18\x01 \x01(\x0e\x32\x41.pogoprotos.networking.game.gamegmtemplates.GameGmTemplatesAction\x12\x17\n\x0frequest_message\x18\x02 \x01(\x0c\x62\x06proto3'
  ,
  dependencies=[pogoprotos_dot_networking_dot_game_dot_gamegmtemplates_dot_game__gm__templates__action__pb2.DESCRIPTOR,])




_GAMEGMTEMPLATESACTIONREQUEST = _descriptor.Descriptor(
  name='GameGmTemplatesActionRequest',
  full_name='pogoprotos.networking.game.gamegmtemplates.GameGmTemplatesActionRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='request_type', full_name='pogoprotos.networking.game.gamegmtemplates.GameGmTemplatesActionRequest.request_type', index=0,
      number=1, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='request_message', full_name='pogoprotos.networking.game.gamegmtemplates.GameGmTemplatesActionRequest.request_message', index=1,
      number=2, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=205,
  serialized_end=349,
)

_GAMEGMTEMPLATESACTIONREQUEST.fields_by_name['request_type'].enum_type = pogoprotos_dot_networking_dot_game_dot_gamegmtemplates_dot_game__gm__templates__action__pb2._GAMEGMTEMPLATESACTION
DESCRIPTOR.message_types_by_name['GameGmTemplatesActionRequest'] = _GAMEGMTEMPLATESACTIONREQUEST
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

GameGmTemplatesActionRequest = _reflection.GeneratedProtocolMessageType('GameGmTemplatesActionRequest', (_message.Message,), {
  'DESCRIPTOR' : _GAMEGMTEMPLATESACTIONREQUEST,
  '__module__' : 'pogoprotos.networking.game.gamegmtemplates.game_gm_templates_action_request_pb2'
  # @@protoc_insertion_point(class_scope:pogoprotos.networking.game.gamegmtemplates.GameGmTemplatesActionRequest)
  })
_sym_db.RegisterMessage(GameGmTemplatesActionRequest)


# @@protoc_insertion_point(module_scope)