FROM ubuntu:14.04

MAINTAINER Johannes 'fish' Ziemke <docker@freigeist.org> @discordianfish

RUN echo deb http://archive.ubuntu.com/ubuntu/ trusty multiverse >> \
    /etc/apt/sources.list
RUN apt-get -qy update && apt-get -qy install python python-cheetah unrar \
    unzip python-yenc par2

RUN    useradd sabnzbd -d /sab -m && chown -R sabnzbd:sabnzbd /sab
VOLUME /sab
ADD  . /sabnzbd

EXPOSE 8080
USER   sabnzbd
ENV    HOME /sab

ENTRYPOINT [ "python", "/sabnzbd/SABnzbd.py", "-s", "0.0.0.0:8080" ]
