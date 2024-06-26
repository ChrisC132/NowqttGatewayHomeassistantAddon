import json
import random
import string
from typing import Dict
import time

import paho.mqtt.client as mqtt
from threading import Thread
import mqtt_task


class NowqttDevices:
    def __init__(self):
        self.devices: Dict[bytearray, Device] = {}

    def has_device(self, device_mac_address):
        for device in self.devices.keys():
            if device == device_mac_address:
                return True
        return False

    def has_device_and_entity(self, device_mac_address, entity_id):
        if self.has_device(device_mac_address):
            return self.devices[device_mac_address].has_entity(entity_id)
        else:
            return False

    def get_entity(self, device_mac_address, entity_id):
        return self.devices[device_mac_address].entities[entity_id]

    def add_element(self,
                    header,
                    mqtt_config,
                    mqtt_subscriptions,
                    mqtt_config_topic,
                    mqtt_config_message_rssi,
                    mqtt_config_topic_rssi,
                    seconds_until_timeout):

        # logging.debug(seconds_until_timeout)
        # logging.debug(mqtt_config)

        # Test if device exists
        if self.has_device(header["device_mac_address_int"]):
            device = self.devices[header["device_mac_address_int"]]
        else:
            mqtt_client_rssi = mqtt.Client(client_id=''.join(random.choices(string.ascii_letters, k=22)))

            device_entity_unique_identifier = bytearray(header["device_mac_address_bytearray"])
            device_entity_unique_identifier.append(0)

            t = Thread(target=mqtt_task.MQTTTask(
                mqtt_client_rssi,
                ["homeassistant/status"],
                device_entity_unique_identifier,
                json.dumps(mqtt_config_message_rssi),
                mqtt_config_topic_rssi,
                mqtt_config_message_rssi["state_topic"]
            ).start_mqtt_task)
            t.daemon = True
            t.start()

            while not mqtt_client_rssi.is_connected():
                time.sleep(0.1)

            new_rssi_entity = Entity(mqtt_config_message_rssi["state_topic"], mqtt_client_rssi, mqtt_config['availability_topic'])
            device = Device(seconds_until_timeout, new_rssi_entity)

            device.rssi_entity.mqtt_publish_availability("online")

        # Test if entity exists
        if not device.has_entity(header["entity_id"]):
            new_client = mqtt.Client(client_id=''.join(random.choices(string.ascii_letters, k=22)))

            t = Thread(target=mqtt_task.MQTTTask(
                new_client,
                mqtt_subscriptions,
                header["mac_address_and_entity_id"],
                json.dumps(mqtt_config),
                mqtt_config_topic,
                mqtt_config["state_topic"]
            ).start_mqtt_task)
            t.daemon = True
            t.start()

            while not new_client.is_connected():
                time.sleep(0.1)

            entity = Entity(mqtt_config["state_topic"], new_client, mqtt_config['availability_topic'])
            device.entities[header["entity_id"]] = entity

        device.set_last_seen_timestamp_to_now()

        self.devices[header["device_mac_address_int"]] = device

    def set_last_seen_timestamp_to_now(self, device_mac_address):
        if self.has_device(device_mac_address):
            self.devices[device_mac_address].set_last_seen_timestamp_to_now()

    def mqtt_disconnect_all(self):
        for device in self.devices.values():
            device.mqtt_disconnect_all()


class Device:
    def __init__(self, seconds_until_timeout, rssi_entity):
        self.last_seen_timestamp = 0
        self.seconds_until_timeout = seconds_until_timeout

        self.entities: Dict[bytearray, Entity] = {}
        self.rssi_entity: Entity = rssi_entity

    def has_entity(self, entity_id):
        return entity_id in self.entities

    def set_last_seen_timestamp_to_now(self):
        self.last_seen_timestamp = int(time.time())

    def mqtt_disconnect_all(self):
        self.rssi_entity.mqtt_publish_availability("offline")

        for device in self.entities.values():
            device.mqtt_disconnect()


class Entity:
    def __init__(self, mqtt_state_topic, mqtt_client, mqtt_availability_topic):
        self.mqtt_state_topic = mqtt_state_topic
        self.mqtt_client = mqtt_client
        self.mqtt_availability_topic = mqtt_availability_topic

    def mqtt_publish(self, message):
        self.mqtt_client.publish(self.mqtt_state_topic, message)
        self.mqtt_client.set_last_known_state(message)

    def mqtt_publish_availability(self, state):
        self.mqtt_client.publish(self.mqtt_availability_topic, state, 0, True)

    def mqtt_disconnect(self):
        self.mqtt_client.disconnect()
