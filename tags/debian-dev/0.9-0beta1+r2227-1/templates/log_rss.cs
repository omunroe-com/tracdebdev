<?xml version="1.0"?>
<!-- RSS generated by Trac v<?cs var:trac.version ?> on <?cs var:trac.time ?> -->
<rss version="2.0">
 <channel><?cs 
  if:project.name_encoded ?>
   <title><?cs var:project.name_encoded ?>: Revisions of <?cs var:log.path ?></title><?cs 
  else ?>
   <title>Revisions of <?cs var:log.path ?></title><?cs 
  /if ?>
  <link><?cs var:base_host ?><?cs var:log.log_href ?></link>
  <description>Trac Log - Revisions of <?cs var:log.path ?></description>
  <language>en-us</language>
  <generator>Trac v<?cs var:trac.version ?></generator><?cs 
  each:item = log.items ?><?cs 
   with:change = log.changes[item.rev] ?>
    <item>
     <author><?cs var:change.author ?></author> 
     <pubDate><?cs var:change.date ?></pubDate>
     <title>Revision <?cs var:item.rev ?>: <?cs var:change.shortlog ?></title>
     <link><?cs var:base_host ?><?cs var:item.changeset_href ?></link>
     <description><?cs var:change.message ?></description>
     <category>Report</category>
    </item><?cs 
   /with ?><?cs 
  /each ?>
 </channel>
</rss>
